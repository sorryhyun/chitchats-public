**🌐 Language: 한국어 | [English](README.en.md)**

# ChitChats

여러 AI 캐릭터들이 함께 대화하는 멀티 에이전트 채팅 애플리케이션입니다. Claude와 Codex 등 다양한 AI 프로바이더를 지원합니다.

본 프로젝트는 *개인 챗지피티 구독* 혹은 *클로드 구독* 을 활용하여 캐릭터챗을 할 수 있게 인터페이스를 제공하는 애플리케이션입니다. 어떠한 정보도 제작자의 서버 등으로 전송되지 않습니다.

![ChitChats 스크린샷](image.png)

## 주요 기능

- **멀티 에이전트 대화** - 고유한 성격을 가진 여러 AI 에이전트가 함께 대화
- **멀티 프로바이더 지원** - 방 생성 시 Claude 또는 Codex 선택 가능
- **실시간 스트리밍** - SSE(Server-Sent Events)로 토큰 단위 실시간 전송 (연결이 끊기면 폴링으로 폴백)
- **에이전트 커스터마이징** - 마크다운 파일과 프로필 사진으로 캐릭터 설정
- **1:1 다이렉트 채팅** - 개별 에이전트와 비공개 대화
- **확장 사고 표시** - 에이전트의 사고 과정 확인 (최대 32K 사고 토큰)
- **음성 (TTS)** - 별도 음성 서버로 에이전트 대사 읽어주기 (선택, `make dev-voice`)
- **대화 내보내기** - 대화 기록을 내려받기
- **JWT 인증** - 비밀번호 기반 보안 인증 및 요청 속도 제한(rate limiting)

## 기술 스택

**백엔드:** FastAPI, SQLAlchemy (async), PostgreSQL, Multi-provider AI (Claude Agent SDK, Codex MCP)
**프론트엔드:** React, TypeScript, Vite, Tailwind CSS

## 사전 요구사항 (Windows)

Windows에서 사용하려면 다음 중 하나 이상을 설치해야 합니다:

- **Claude Code** - [claude.ai/code](https://claude.ai/code)에서 설치
- **Codex** - [GitHub Releases](https://github.com/openai/codex/releases)에서 Windows 버전 다운로드

방 생성 시 설치된 프로바이더를 선택할 수 있습니다.

## 설치

### 윈도우

PowerShell에서 아래 한 줄을 실행하세요. 최신 릴리즈의 `ChitChats.exe`와 기본 에이전트를
`%LOCALAPPDATA%\ChitChats`에 설치하고 시작 메뉴/바탕화면 바로가기를 만듭니다.

```powershell
irm https://github.com/sorryhyun/chitchats-public/releases/latest/download/install.ps1 | iex
```

설치 위치 등 옵션을 지정하려면 스크립트를 내려받아 실행하세요:

```powershell
irm https://github.com/sorryhyun/chitchats-public/releases/latest/download/install.ps1 -OutFile install.ps1
.\install.ps1 -InstallDir D:\ChitChats
```

설치 후 시작 메뉴의 **ChitChats**를 실행하면 첫 실행 시 비밀번호를 설정하고 브라우저가 열립니다.

### macOS / 리눅스 / WSL

```bash
curl -fsSL https://github.com/sorryhyun/chitchats-public/releases/latest/download/install.sh | bash
```

최신 릴리즈를 `~/.chitchats`에 설치하고, 의존성 설치와 `.env` 생성(비밀번호 입력)까지 진행한 뒤
`~/.local/bin/chitchats` 실행 파일을 만듭니다. **Node.js 20+** 가 필요하며, `uv`는 없으면 자동으로 설치됩니다.

```bash
chitchats            # 백엔드 + 프론트엔드 실행
chitchats sqlite     # SQLite로 실행 (PostgreSQL 불필요)
chitchats voice      # 음성 TTS 서버까지 실행
chitchats update     # 최신 릴리즈로 업데이트 (.env / DB / 에이전트 유지)
chitchats help       # 전체 명령어
```

주요 설치 옵션:

```bash
curl -fsSL <위 URL> | bash -s -- --dir ~/apps/chitchats --version v1.2.0
```

http://localhost:5173 에서 설정한 비밀번호로 로그인하세요. (백엔드: http://localhost:8001)

PostgreSQL을 쓰려면 `createdb chitchats` 후 `.env`의 `USE_SQLITE`를 주석 처리하고 `DATABASE_URL`을 설정하세요.
자세한 내용은 [docs/SETUP.md](docs/SETUP.md)를 참조하세요.

### 소스에서 실행 (개발자용)

```bash
git clone https://github.com/sorryhyun/chitchats-public.git
cd chitchats-public
make install         # 의존성 설치
make env             # .env 생성 (비밀번호 입력)
make dev             # 실행
```

## 시뮬레이션

```bash
make simulate ARGS='-p "비밀번호" -s "AI 윤리에 대해 토론" -a "alice,bob,charlie"'
```

## 에이전트 설정

에이전트는 `agents/` 폴더의 마크다운 파일로 설정합니다. 변경사항은 재시작 없이 즉시 반영됩니다.

**폴더 구조:**
```
agents/
  캐릭터명/
    ├── in_a_nutshell.md      # 캐릭터 요약 (3인칭)
    ├── characteristics.md     # 성격 특성 (3인칭)
    ├── recent_events.md      # 최근 사건 (자동 업데이트)
    ├── consolidated_memory.md # 장기 기억 (선택)
    └── profile.png           # 프로필 사진 (선택)
```

자세한 설정 옵션은 [CLAUDE.md](CLAUDE.md)를 참조하세요.

## 명령어

설치 스크립트로 설치한 경우 (macOS / 리눅스 / WSL):

```bash
chitchats          # 실행
chitchats update   # 업데이트
chitchats stop     # 서버 중지
```

소스에서 실행하는 경우:

```bash
make dev           # 풀스택 실행 (PostgreSQL)
make dev-voice     # 풀스택 + 음성 TTS 서버 (포트 8002)
make dev-sqlite    # 풀스택 실행 (SQLite)
make install       # 의존성 설치
make build-exe     # 윈도우 단독 실행 파일 빌드
make agents-zip    # 에이전트 배포용 zip 생성
make stop          # 서버 중지
make clean         # 빌드 파일 정리
```

## API

인증, 방, 에이전트, 메시징, SSE 스트리밍을 위한 REST API를 제공합니다. `/auth/*`와 `/health`를 제외한 모든 엔드포인트는 `X-API-Key` 헤더로 JWT 인증이 필요합니다.

전체 API 레퍼런스는 [backend/README.md](backend/README.md)를 참조하세요.

## 배포

**배포 전략:**
- **백엔드:** 로컬 머신 + Cloudflare 터널 (`make run-tunnel-backend`, 또는 클라우드 호스팅)
- **프론트엔드:** Vercel (또는 기타 정적 호스팅)
- **CORS:** 백엔드 `.env`의 `FRONTEND_URL`로 설정
- **인증:** 비밀번호/JWT 기반

`make prod`는 백엔드 실행, 터널 생성, Vercel 환경 변수 갱신 및 재배포를 한 번에 수행합니다. 자세한 내용은 [docs/SETUP.md](docs/SETUP.md)를 참조하세요.

## 설정

**필수:** 백엔드 `.env` 파일에 `API_KEY_HASH`, `JWT_SECRET` 설정 (`DATABASE_URL`은 기본값 사용 가능)

인증 설정은 [docs/SETUP.md](docs/SETUP.md), 전체 설정 옵션은 [backend/README.md](backend/README.md)를 참조하세요.
