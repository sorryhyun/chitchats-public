**🌐 Language: 한국어 | [English](README.en.md)**

# ChitChats

여러 AI 캐릭터들이 함께 대화하는 멀티 에이전트 채팅 애플리케이션입니다. Claude와 Codex 등 다양한 AI 프로바이더를 지원합니다.

본 프로젝트는 *개인 챗지피티 구독* 혹은 *클로드 구독* 을 활용하여 캐릭터챗을 할 수 있게 인터페이스를 제공하는 애플리케이션입니다. 어떠한 정보도 제작자의 서버 등으로 전송되지 않습니다.

## 주요 기능

- **멀티 에이전트 대화** - 고유한 성격을 가진 여러 AI 에이전트가 함께 대화
- **멀티 프로바이더 지원** - 방 생성 시 Claude 또는 Codex 선택 가능
- **실시간 업데이트** - HTTP 폴링을 통한 실시간 메시지 업데이트
- **에이전트 커스터마이징** - 마크다운 파일과 프로필 사진으로 캐릭터 설정
- **1:1 다이렉트 채팅** - 개별 에이전트와 비공개 대화
- **확장 사고 표시** - 에이전트의 사고 과정 확인 (32K 토큰)
- **JWT 인증** - 비밀번호 기반 보안 인증

## 기술 스택

**백엔드:** FastAPI, SQLAlchemy (async), SQLite, Multi-provider AI (Claude SDK, Codex CLI)
**프론트엔드:** React, TypeScript, Vite, Tailwind CSS

## 사전 요구사항 (Windows)

Windows에서 사용하려면 다음 중 하나 이상을 설치해야 합니다:

- **Claude Code** - [claude.ai/code](https://claude.ai/code)에서 설치
- **Codex** - [GitHub Releases](https://github.com/openai/codex/releases)에서 Windows 버전 다운로드

방 생성 시 설치된 프로바이더를 선택할 수 있습니다.

## 빠른 시작 (윈도우)

릴리즈에서 최신 exe를 다운로드 받아 실행해주세요

## 시작 (WSL, 리눅스 등)

### 1. 의존성 설치

```bash
make install
```

### 2. 인증 설정

```bash
make generate-hash  # 비밀번호 해시 생성
python -c "import secrets; print(secrets.token_hex(32))"  # JWT 시크릿 생성
cp .env.example .env  # .env 파일에 API_KEY_HASH와 JWT_SECRET 추가
```

자세한 내용은 [SETUP.md](SETUP.md)를 참조하세요.

### 3. 실행

```bash
make dev
```

http://localhost:5173 에서 비밀번호로 로그인하세요.

## 시뮬레이션

```bash
make simulate ARGS='-s "AI 윤리에 대해 토론" -a "alice,bob,charlie"'
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

```bash
make dev           # 풀스택 실행
make install       # 의존성 설치
make stop          # 서버 중지
make clean         # 빌드 파일 정리
```

## API

인증, 방, 에이전트, 메시징을 위한 REST API를 제공합니다. `/auth/*`와 `/health`를 제외한 모든 엔드포인트는 `X-API-Key` 헤더로 JWT 인증이 필요합니다.

전체 API 레퍼런스는 [backend/README.md](backend/README.md)를 참조하세요.

## 배포

**배포 전략:**
- **백엔드:** 로컬 머신 + ngrok 터널 (또는 클라우드 호스팅)
- **프론트엔드:** Vercel (또는 기타 정적 호스팅)
- **CORS:** 백엔드 `.env`의 `FRONTEND_URL`로 설정
- **인증:** 비밀번호/JWT 기반

자세한 내용은 [SETUP.md](SETUP.md)를 참조하세요.

## 설정

**필수:** 백엔드 `.env` 파일에 `API_KEY_HASH`, `JWT_SECRET` 설정

인증 설정은 [SETUP.md](SETUP.md), 전체 설정 옵션은 [backend/README.md](backend/README.md)를 참조하세요.
