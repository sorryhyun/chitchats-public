# Codex CLI: 아키텍처 결정 사항

이 문서는 Codex CLI를 ChitChats에 통합할 때 **왜** 현재 방식을 선택했는지 설명합니다. Codex 소스 코드 분석을 기반으로 작성되었습니다.

---

## 목차

1. [빠른 시작](#빠른-시작)
2. [핵심 문제](#핵심-문제)
3. [왜 App Server 모드인가 (MCP Server가 아닌)](#왜-app-server-모드인가-mcp-server가-아닌)
4. [왜 에이전트별 인스턴스인가](#왜-에이전트별-인스턴스인가)
5. [왜 세션 초기화 시점에 Instructions를 설정하는가](#왜-세션-초기화-시점에-instructions를-설정하는가)
6. [왜 특정 기능을 비활성화하는가](#왜-특정-기능을-비활성화하는가)
7. [구현 참조](#구현-참조)
8. [부록: Codex 내부 구조](#부록-codex-내부-구조)

---

## 빠른 시작

### 설치

```bash
npm install -g @openai/codex
codex login              # 인증 (브라우저 열림)
codex login status       # 인증 상태 확인
```

### App Server 실행

```bash
# 기본 실행
codex app-server

# 커스텀 instructions 설정
codex app-server -c "base_instructions=You are a helpful assistant"

# 채팅 용도로 shell/web 비활성화
codex app-server \
  -c "features.shell_tool=false" \
  -c "web_search=disabled"
```

### JSON-RPC 프로토콜 (stdio 통신)

**스레드 생성:**

```json
{"method": "thread/start", "params": {"baseInstructions": "You are Alice..."}, "id": 1}
```

응답: `{"result": {"threadId": "thread_abc123"}, "id": 1}`

**메시지 전송:**

```json
{"method": "turn/start", "params": {"threadId": "thread_abc123", "input": [{"type": "text", "text": "Hello!"}]}, "id": 2}
```

스트리밍 알림이 뒤따름 (`id` 필드 없음):

```json
{"method": "item/agentMessage/delta", "params": {"delta": "Hi there"}}
{"method": "item/agentMessage/delta", "params": {"delta": "! How can I help?"}}
{"method": "turn/completed", "params": {"status": "completed"}}
```

**스레드 재개 (재시작 후):**

```json
{"method": "thread/resume", "params": {"threadId": "thread_abc123"}, "id": 3}
```

### 주요 이벤트

| 이벤트 | 용도 |
|--------|------|
| `turn/started` | 턴 처리 시작 |
| `turn/completed` | 턴 완료 |
| `item/agentMessage/delta` | 스트리밍 텍스트 청크 |
| `item/reasoning/textDelta` | 스트리밍 사고 과정 |
| `item/mcpToolCall/completed` | MCP 도구 호출 완료 |

---

## 핵심 문제

ChitChats는 실시간 채팅방에서 서로 다른 성격을 가진 여러 AI 에이전트를 실행해야 합니다. 각 에이전트에게 필요한 것:

- **고유한 시스템 프롬프트** (성격, 배경, 행동 방식)
- **세션 연속성** (대화 컨텍스트 유지)
- **커스텀 도구** (에이전트별 MCP 서버)
- **격리** (에이전트 간 컨텍스트 누출 방지)

Codex CLI는 세 가지 통합 모드를 제공합니다. 각 모드를 이 요구사항에 맞춰 평가했습니다.

---

## 왜 App Server 모드인가 (MCP Server가 아닌)

### 세 가지 옵션

| 모드 | 작동 방식 | 세션 상태 |
|------|----------|----------|
| `codex` CLI | 쿼리마다 프로세스 생성 | 없음 (상태 없음) |
| `codex-mcp-server` | MCP 프로토콜로 연결 | 호출 단위만 |
| `codex app-server` | 장기 실행 JSON-RPC 서버 | 스레드 기반 지속 |

### 왜 쿼리마다 `codex`를 실행하지 않는가?

메시지마다 새 프로세스를 생성하면 심각한 오버헤드가 발생합니다:

```text
사용자가 메시지 전송
  → codex 프로세스 생성 (~2-3초)
  → 설정 로드, 인증
  → 단일 메시지 처리
  → 종료하고 모든 컨텍스트 손실
```

실시간 응답이 필요한 채팅 애플리케이션에서 이 지연은 허용할 수 없습니다. 더 중요한 것은, **메시지 간 대화 컨텍스트를 유지할 방법이 없다**는 것입니다.

### 왜 MCP Server가 아닌가?

`codex-mcp-server`는 소스 코드를 분석해서 발견한 근본적인 제한이 있습니다:

```text
MCP Client (이미지 지원)
    ↓
MCP Server (텍스트 전용 인터페이스) ← 병목
    ↓
Codex Core (완전한 멀티모달 지원)
```

MCP 서버는 `String` 프롬프트만 받습니다:

```rust
// codex-rs/mcp-server/src/codex_tool_config.rs
pub struct CodexToolCallParam {
    pub prompt: String,  // 텍스트만 - 이미지 미지원
}
```

Codex 코어가 `UserInput::Image`와 `UserInput::LocalImage`를 지원하지만, MCP 프로토콜 인터페이스는 입력을 `UserInput::Text`로만 래핑합니다.

사용자가 이미지를 공유하는 채팅 애플리케이션에서 이것은 치명적입니다.

### 왜 App Server가 최선인가

`codex app-server`가 제공하는 것:

1. **스레드 기반 세션** - 한 번 생성하면 무한히 재개 가능
2. **완전한 멀티모달 지원** - Codex 코어에 직접 접근 (MCP 병목 없음)
3. **스트리밍 이벤트** - JSON-RPC를 통한 실시간 텍스트/사고 델타
4. **스레드별 instructions** - 각 스레드가 자체 시스템 프롬프트 유지

```text
사용자가 메시지 전송
  → 기존 app-server 인스턴스로 라우팅
  → 스레드 재개 (즉시)
  → 실시간으로 응답 스트리밍
  → 다음 메시지를 위해 스레드 유지
```

---

## 왜 에이전트별 인스턴스인가

### 대안: 공유 인스턴스

더 간단한 접근법은 하나의 `codex app-server`가 모든 에이전트를 서비스하는 것입니다:

```text
단일 App Server
├── 방 1의 Alice용 스레드
├── 방 1의 Bob용 스레드
├── 방 2의 Alice용 스레드
└── ...
```

**문제점:**

- MCP 서버는 시작 시점에 설정되며, 스레드별로 설정할 수 없음
- 에이전트별 도구 (메모리, 액션)를 스레드별로 다르게 할 수 없음
- 크래시 시 모든 에이전트가 동시에 영향받음

### 우리의 접근법: 에이전트별 인스턴스

```text
CodexAppServerPool (싱글톤)
├── Agent "Alice" → CodexAppServerInstance (Alice의 MCP 설정)
├── Agent "Bob"   → CodexAppServerInstance (Bob의 MCP 설정)
└── ...
```

각 인스턴스는 시작 시점에 에이전트별 MCP 서버가 내장됩니다:

```python
mcp_servers = {
    "memory_server": {
        "env": {"AGENT_NAME": "alice"}  # 에이전트별
    }
}
```

**장점:**

- 에이전트 간 완전한 격리
- 우회 없이 에이전트별 도구 사용
- 크래시 격리 (한 에이전트 다운 ≠ 모든 에이전트 다운)
- 독립적인 스케일링과 라이프사이클

**트레이드오프:** 더 높은 메모리 사용량 (에이전트당 하나의 프로세스). 다음으로 완화:

- 유휴 타임아웃 제거 (기본: 10분)
- LRU 제거를 통한 최대 인스턴스 제한
- 지연 생성 (첫 상호작용 시 인스턴스 생성)

---

## 왜 세션 초기화 시점에 Instructions를 설정하는가

### Codex의 제약

Codex 소스를 분석한 결과:

> Instructions는 초기화 시점(세션/스레드 생성)에 적용되며, 턴마다 적용되지 않음

해결 순서 (`codex.rs:285-294`에서):

1. `config.base_instructions` 오버라이드 (CLI/API)
2. `conversation_history.get_base_instructions()` (세션 지속성)
3. `model_info.get_model_instructions()` (모델 기본값)

이것이 의미하는 바:

- `base_instructions`는 스레드 생성 시 설정됨
- 대화 중간에 성격을 바꾸려면 새 스레드가 필요함
- 턴별 instruction 변경은 무시됨

### ChitChats에 대한 함의

에이전트 성격이 `base_instructions`에 정의되므로, 우리는:

1. **첫 상호작용에서 스레드 생성** - 에이전트의 전체 시스템 프롬프트와 함께
2. **thread_id를 데이터베이스에 저장** - 세션 연속성을 위해
3. **같은 방의 후속 메시지에 기존 스레드 재개**

에이전트의 성격 파일이 변경되면 스레드를 무효화해야 하지만, 실제로 이런 경우는 드뭅니다.

### `instructions` Config 필드는 죽은 코드

놀라운 발견: `config.toml`의 `instructions` 필드는 **정의되었지만 읽히지 않습니다**:

```rust
// config/mod.rs의 ConfigToml 구조체
pub instructions: Option<String>,  // 사용되지 않음!
```

코드베이스 어디에서도 `cfg.instructions`를 읽지 않습니다. 대신 `base_instructions`나 `model_instructions_file`을 사용하세요.

---

## 왜 특정 기능을 비활성화하는가

### 롤플레이 유즈케이스

ChitChats 에이전트는 채팅방의 캐릭터이지, 코딩 어시스턴트가 아닙니다. Codex의 기본 기능은 이에 맞지 않습니다:

| 기능 | 비활성화 이유 |
|------|-------------|
| `shell_tool` | 캐릭터가 시스템 명령을 실행하면 안 됨 |
| `web_search` | 몰입을 깨고 현실 세계 정보가 누출됨 |
| `view_image` | 이미지를 직접 처리하며 Codex 도구 사용 안 함 |
| Skills (`~/.codex/skills/`) | 자동 주입된 프롬프트가 캐릭터를 깸 |
| `AGENTS.md` 픽업 | 프로젝트 파일을 읽어 성격을 오염시킴 |

### Skills 주입 문제

Codex는 `~/.codex/skills/`의 instructions를 모든 세션에 자동 로드합니다. 롤플레이에서:

```text
System: You are Alice, a shy librarian...
Skills: [자동 주입됨] You are a helpful coding assistant...
```

이것은 캐릭터 몰입을 파괴합니다. 해결책: `chmod 000 ~/.codex/skills`

### 작업 디렉토리 오염

Codex는 작업 디렉토리에서 `AGENTS.md`와 다른 파일을 읽습니다. ChitChats 저장소에서 실행하면:

```text
System: You are Alice...
Codex: [AGENTS.md 읽음] 아, 여러 에이전트가 설정되어 있네요...
```

해결책: 빈 임시 디렉토리를 `cwd`로 사용:

```python
cwd = Path(tempfile.gettempdir()) / "codex-empty"
```

---

## 구현 참조

### 주요 파일

| 파일 | 용도 |
|------|------|
| `backend/providers/codex/app_server_pool.py` | LRU 제거가 있는 싱글톤 풀 |
| `backend/providers/codex/app_server_instance.py` | 에이전트별 프로세스 라이프사이클 |
| `backend/providers/codex/transport.py` | stdio를 통한 JSON-RPC |
| `backend/providers/codex/constants.py` | 이벤트 타입, 세션 복구 |

### 설정 기본값

```bash
CODEX_MAX_INSTANCES=10      # 최대 동시 인스턴스
CODEX_IDLE_TIMEOUT=600      # 종료 전 유휴 시간 10분
```

### 세션 복구

인스턴스가 재시작되면 (크래시, 유휴 타임아웃), 스레드가 무효화됩니다. `SessionRecoveryError`로 처리합니다:

1. Codex 에러에서 무효한 thread_id 감지
2. 호출자에게 `SessionRecoveryError` 발생
3. 호출자가 전체 대화 기록 재구축
4. 완전한 컨텍스트로 새 스레드 생성

이로써 사용자는 "세션 만료" 에러를 보지 않습니다—대화가 매끄럽게 계속됩니다.

---

## 요약

| 결정 | 근거 |
|------|------|
| App Server 모드 | 세션 지속성, 완전한 멀티모달, 스트리밍 |
| 에이전트별 인스턴스 | MCP 격리, 크래시 격리, 에이전트별 도구 |
| 초기화 시 Instructions | Codex 제약—instructions는 턴별이 아님 |
| shell/web/skills 비활성화 | 롤플레이 유즈케이스는 몰입이 필요 |
| 빈 작업 디렉토리 | 파일 오염 방지 |
| DB에 스레드 저장 | 인스턴스 재시작 후에도 재개 |

---

## 부록: Codex 내부 구조

이 섹션은 소스 코드 분석을 통해 발견한 Codex CLI 내부 구조를 문서화합니다.

### Instruction 관련 필드

서로 다른 목적을 가진 **여러 instruction 필드**가 있습니다:

| 필드 | 위치 | 목적 | 상태 |
|------|------|------|------|
| `instructions` | ConfigToml | 시스템 instructions | **죽은 코드** |
| `base_instructions` | Config (런타임) | 실제 시스템 프롬프트 | 활성 |
| `developer_instructions` | Config | 별도 "developer" 역할 | 활성 |
| `user_instructions` | Config | AGENTS.md 파일에서 | 활성 |
| `model_instructions_file` | ConfigToml/Profile | instructions 파일 경로 | 활성 |

### 도구 비활성화 참조

**비활성화 가능한 도구:**

| 도구 | 설정 옵션 |
|------|----------|
| Shell 도구 | `features.shell_tool = false` |
| 웹 검색 | `web_search = "disabled"` |
| 이미지 보기 | `tools_view_image = false` |
| 패치 적용 | `include_apply_patch_tool = false` |
| 협업 도구 | `features.collab = false` |

**비활성화 불가능한 도구** (`build_specs()`에 하드코딩됨):

- `plan` - 계획 업데이트 도구
- `list_mcp_resources`
- `list_mcp_resource_templates`
- `read_mcp_resource`

### MCP 서버 도구 필터링

`config.toml`을 통한 서버별 도구 필터링:

```toml
[mcp_servers.my_server]
enabled_tools = ["tool1", "tool2"]   # 화이트리스트
disabled_tools = ["tool3"]            # 블랙리스트 (두 번째로 적용)
```

### CLI 예제

```bash
# Shell 도구 비활성화
codex app-server -c "features.shell_tool=false"

# 웹 검색 비활성화
codex app-server -c "web_search=disabled"

# 커스텀 instructions 설정
codex app-server -c "base_instructions=You are Alice..."
```
