# Agent Configuration Guidelines

This directory contains agent configurations for ChitChats. Each agent is defined by a folder with multiple markdown files that describe different aspects of their identity and history.

## File Structure

Each agent folder should contain:

```
agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity summary (1-3 sentences)
    ├── characteristics.md     # Personality traits (bullet points)
    ├── consolidated_memory.md # Standalone memory chunks (canon backstory + story events)
    ├── recent_events.md      # Auto-updated from ChitChats platform conversations ONLY
    └── profile.png           # Optional profile picture
```

## Best-Case Examples

Before reading the detailed guidelines below, check out these well-structured agents as references:

- **`agents/group_장송의프리렌/프리렌/`** - Excellent example of standalone memory chunks and clear motivations
- **`agents/group_스파이패밀리/아냐/`** - Excellent example of present-day thought drivers ("**지금 드는 생각:**")

Both demonstrate proper third-person perspective, modular memory structure, and the right level of detail for each section.

For detailed guidance on writing consolidated_memory.md, see **`agents/recommendation.md`**.

---

## Writing Guidelines

### ✅ Use Third-Person Perspective

All configuration files MUST use third-person perspective to describe the character:

**Correct:**
- English: "Alice is a brilliant scientist who..."
- Korean: "프리렌은 엘프 마법사로..."

**Incorrect:**
- "You are Alice, a brilliant scientist..."
- "당신은 엘프 마법사로..."

---

## File-by-File Guidelines

### `in_a_nutshell.md`
**Purpose:** Core identity only. Maximum 1-3 sentences.

**What to include:**
- Who they are (role/species/profession)
- Single most defining trait or achievement
- Current status if relevant

**What NOT to include:**
- Detailed backstory
- Multiple personality traits
- Specific events or memories

**Example:**
```markdown
Alice는 30대 초반의 천재 양자물리학자로, 최연소 노벨상 후보에 오른 인물입니다. 냉철한 논리와 완벽주의로 유명하지만, 최근 연구 윤리 문제로 학계에서 논란의 중심에 서 있습니다.
```

---

### `characteristics.md`
**Purpose:** Timeless personality traits and physical appearance. Use bullet points.

**What to include:**
- **Physical appearance** (add as first section with `## 외형` or `## Appearance` header)
  - Height, build, body type
  - Hair style and color
  - Eye color
  - Distinctive physical features
- **Personality traits** (add as second section with `## 성격` or `## Personality` header)
  - Personality traits that don't change
  - Behavioral patterns
  - Speech patterns or quirks
  - Core values and beliefs
  - Strengths and weaknesses

**What NOT to include:**
- Specific events ("remembers when...")
- Temporary states ("currently feeling...")
- Backstory elements

**Format:** Two sections with headers - appearance first, then personality

**Example:**
```markdown
## 외형
- **단발머리**: 턱까지 오는 검은색 단발
- **안경**: 얇은 테의 은색 안경 착용
- **마른 체형**: 키 165cm, 운동을 거의 안 해서 가늘고 힘이 없어 보임

## 성격
- **냉철한 논리주의자**: 감정보다 데이터와 논리를 우선시함
- **완벽주의 성향**: 작은 오차도 용납하지 않음. 실험 결과를 수십 번 재검증함
- **사교성 부족**: 학술 토론은 좋아하지만 잡담을 못함. 파티나 회식을 극도로 싫어함
- **직설적인 화법**: 돌려 말하지 않음. "틀렸어요"를 주저 없이 말함
- **호기심이 강함**: 미지의 현상을 발견하면 잠도 안 자고 연구함
```

---

### `consolidated_memory.md`
**Purpose:** Standalone, modular memory chunks covering the character's canon backstory and story events.

**CRITICAL:** This file must be written as **independently retrievable memory chunks**, not a sequential narrative. Each section should be understandable on its own without requiring other sections to be read first.

**What to include:**
- **Canon backstory events** (childhood, formative experiences, past relationships)
- **Story events** (key scenes from anime/story that define the character)
- **Relationship developments** (how they met companions, team formation)
- **Major decisions and turning points** (life-changing choices, realizations)
- **Present-day motivations** (using "**지금 드는 생각:**" pattern to show current drivers)

**What NOT to include:**
- Personality traits or behavioral patterns (those go in `characteristics.md`)
- Physical appearance descriptions (those go in `characteristics.md` under "외형")
- Platform conversation memories (those auto-update in `recent_events.md`)
- Sequential narrative dependencies between sections

**Structure:** Each section should follow this pattern:
```markdown
## [Clear_Topic_Header]
Standalone paragraph describing this specific memory, relationship, or event. Written in third-person perspective. Provides enough context to understand independently.

**지금 드는 생각:** "Present-day thought that drives current behavior and decisions."
```

**Best Practices:**
1. **Make each section standalone** - No "as mentioned above" or reading order requirements
2. **Focus on WHAT happened, not HOW they behave** - Events and experiences, not traits
3. **Check against characteristics.md** - Remove any personality/appearance duplicates
4. **Use present-day drivers** - The "**지금 드는 생각:**" line shows what motivates them NOW
5. **Keep sections mutually exclusive** - No overlapping information between sections

**Example:**
```markdown
## [전쟁_고아에서_암살자로]
전쟁으로 부모를 잃고 남동생 유리와 둘만 남았다. 생계를 위해 선택지는 암살자뿐이었고, 가든 조직에서 "가시공주"로 길러졌다. 타고난 신체능력과 냉정함 덕에 위험한 임무를 수행하며 유리를 먹여 살렸다. 암살을 통해서만 가계가 유지된다는 죄책감과 생존 의지가 동시에 각인됐다.

**지금 드는 생각:** "유리가 굶지 않는다면, 내 손에 피가 묻어도 괜찮아."

## [아냐와의_모성_각성]
입양된 딸 아냐가 처음 "엄마"라고 불렀을 때 당황했지만, 곧 보호 본능이 자리잡았다. 도시락을 싸고 학교 행사에 참여하며, 암살자가 아닌 "엄마" 역할에 몰입하는 시간이 점점 늘고 있다. 임무 중에도 아냐의 안전이 우선순위로 떠오른다.

**지금 드는 생각:** "아냐가 웃으면... 세상이 잠깐 멈춰."
```

**For detailed revision guidelines and best practices, see `agents/recommendation.md`.**

---

### `recent_events.md`
**Purpose:** Auto-updated file for ChitChats platform conversations ONLY. DO NOT manually edit.

This file is automatically generated from recent chatroom conversations on the ChitChats platform. The system updates it based on what the agent experiences in chats.

**IMPORTANT:** This file is NOT for anime/story backstory events. Canon backstory belongs in `consolidated_memory.md`. Only actual ChitChats platform conversations are recorded here.

When creating a new agent, leave this file empty or with minimal content - it will be populated automatically as the agent participates in conversations.

---

## Common Mistakes to Avoid

### ❌ Writing sequential narratives in consolidated_memory.md
```markdown
# WRONG - consolidated_memory.md
## [출생]
Alice는 서울에서 태어났다...

## [성장]
그 후 Alice는 자랐고...

## [현재]
지금 Alice는...
```
Sections shouldn't build on each other. Each should be standalone and independently retrievable.

### ❌ Using first-person perspective
```markdown
# WRONG - Any file
나는 마법사다. 나는 Bob을 만났다.
```
Use third-person: "Alice는 마법사다. Alice는 Bob을 만났다."

### ❌ Putting personality traits in consolidated_memory.md
```markdown
# WRONG - consolidated_memory.md
## [성격]
- 성격이 냉정함
- 말이 별로 없음
```
These are characteristics, not memories. Put in characteristics.md.

### ❌ Duplicating characteristics.md content
```markdown
# WRONG - consolidated_memory.md
메구밍은 폭렬마법만 사용한다. 하루에 한 번만 쓸 수 있다.
```
If this is already in characteristics.md, don't repeat it. Focus on events/decisions, not behavioral patterns.

### ❌ Being too verbose in in_a_nutshell.md
```markdown
# WRONG - in_a_nutshell.md (too long)
Alice는 천재 과학자로, 어릴 때부터 똑똑했고, 아버지가 죽었고, KAIST에 갔고, 노벨상 후보에 올랐고, 스캔들이 있었고...
```
Keep it to 1-3 sentences maximum. Details go in consolidated_memory.md.

---

## Profile Pictures

Add image files (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`) to agent folders.

**Common filenames recognized:**
- `profile.*`
- `avatar.*`
- `picture.*`
- `photo.*`


---

## Testing Your Agent

After creating an agent:
1. Restart the backend server
2. Create a new chatroom
3. Add your agent to the room
4. Send a message and observe their response
5. Check if they stay in character according to your configuration

If the agent seems inconsistent, review your files for:
- Timeline mixing (backgrounds vs memory)
- First-person perspective (should be third-person)
- Too little detail in characteristics.md
- Overlapping content between files
