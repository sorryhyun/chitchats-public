#!/bin/bash
# Test agent capabilities by asking them questions sequentially
# Multiple agents are tested in parallel
# Run with: chmod +x test_agent_questions.sh && ./test_agent_questions.sh

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

# Parse flags
QUIET=false
SHOW_THINKING=false
while [[ "$1" == -* ]]; do
    case "$1" in
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -t|--thinking)
            SHOW_THINKING=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Helper function for quiet-aware echo
qecho() {
    if [ "$QUIET" != "true" ]; then
        echo -e "$@"
    fi
}

# Load configuration from .env if it exists
if [ -f ".env" ]; then
    # Load JWT token
    JWT_TOKEN=$(grep '^JWT_TOKEN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
    # Load password if available
    PASSWORD=$(grep '^CHITCHATS_PASSWORD=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

# Configuration
QUESTIONS_PER_AGENT=${1:-10}  # Questions to ask each agent (default: 10)
API_BASE="${BACKEND_URL:-http://localhost:8001}"
PASSWORD="${PASSWORD:-${CHITCHATS_PASSWORD:-}}"  # From .env, env var, or will prompt
JWT_TOKEN="${JWT_TOKEN:-}"
CHECK_ANT="${CHECK_ANT:-0}"  # Show anthropic model info if set to 1

# Agents to test (can be specified as arguments after question count)
# Example: ./test_agent_questions.sh 10 봇치 프리렌 치즈루 코베니
[ $# -gt 0 ] && shift  # Remove first argument (question count) if present
if [ $# -gt 0 ]; then
    AGENTS_TO_TEST=("$@")
else
    AGENTS_TO_TEST=("프리렌" "페른") 
    # "덴지" "마키마" "릿카" "유이" "치카" "리카" "레나"
    # AGENTS_TO_TEST=("마키마" "릿카" "유이" "치카" "에루")
fi

# Generate unique timestamp prefix for this batch
BATCH_ID=$(date +%s)

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is required but not installed${NC}"
    echo "Install with: sudo apt-get install jq (Debian/Ubuntu) or brew install jq (macOS)"
    exit 1
fi

# Function to make API calls
api_call() {
    local method=$1
    local endpoint=$2
    local data=$3
    local auth_header=$4

    local args=(-s -X "$method" "$API_BASE$endpoint")

    if [ -n "$auth_header" ]; then
        args+=(-H "X-API-Key: $auth_header")
    fi

    if [ -n "$data" ]; then
        args+=(-H "Content-Type: application/json" -d "$data")
    fi

    curl "${args[@]}"
}

# Function to authenticate and get JWT token
authenticate() {
    if [ -n "$JWT_TOKEN" ]; then
        [ "$QUIET" != "true" ] && echo -e "${YELLOW}Using existing JWT token...${NC}" >&2
        echo "$JWT_TOKEN"
        return
    fi

    if [ -z "$PASSWORD" ]; then
        echo -e "${YELLOW}Enter password:${NC}" >&2
        read -s PASSWORD
        echo "" >&2
    fi

    local response=$(api_call POST "/auth/login" "{\"password\":\"$PASSWORD\"}" "")
    local token=$(echo "$response" | jq -r '.api_key // empty')

    if [ -z "$token" ]; then
        echo -e "${RED}Authentication failed${NC}" >&2
        echo "$response" | jq '.' 2>/dev/null || echo "$response" >&2
        exit 1
    fi

    echo "$token"
}

# Function to log with colors to terminal, plain text to file
log() {
    local message="$1"
    local output_file="$2"

    # Print with colors to terminal (unless quiet mode)
    if [ "$QUIET" != "true" ]; then
        echo -e "$message"
    fi

    # Strip ANSI codes and write to file
    if [ -n "$output_file" ]; then
        echo -e "$message" | sed 's/\x1b\[[0-9;]*m//g' >> "$output_file"
    fi
}

# Function to extract questions from markdown file
extract_questions() {
    local file=$1
    local max_questions=$2

    # Extract questions (simple numbered format)
    local questions=()
    local current_q=""
    local q_count=0

    while IFS= read -r line; do
        # Match question number (e.g., "1. Question text...")
        if [[ $line =~ ^[0-9]+\.[[:space:]](.+) ]]; then
            if [ $q_count -ge $max_questions ]; then
                break
            fi
            if [ -n "$current_q" ]; then
                questions+=("$current_q")
            fi
            current_q="${BASH_REMATCH[1]}"
            ((q_count++))
        # Skip empty lines and headers
        elif [[ -z "$line" || $line =~ ^# ]]; then
            continue
        fi
    done < "$file"

    # Add last question
    if [ -n "$current_q" ] && [ $q_count -le $max_questions ]; then
        questions+=("$current_q")
    fi

    # Print array as lines
    printf '%s\n' "${questions[@]}"
}

# Function to test a single question (runs in its own process)
test_single_question() {
    local agent_name=$1
    local agent_id=$2
    local q_num=$3
    local total_questions=$4
    local question=$5
    local token=$6
    local temp_output_file=$7

    # Create new room for this question (paused to exclude from background scheduler)
    local room_name="Q${q_num}_${agent_name}_${BATCH_ID}"
    local room_data=$(api_call POST "/rooms" "{\"name\":\"$room_name\",\"max_interactions\":5,\"is_paused\":true}" "$token")
    local room_id=$(echo "$room_data" | jq -r '.id // empty')

    if [ -z "$room_id" ]; then
        echo "[ERROR] Failed to create room" > "$temp_output_file"
        return 1
    fi

    # Add agent to room
    local add_response=$(api_call POST "/rooms/$room_id/agents/$agent_id" "" "$token")
    if ! echo "$add_response" | jq -e '.id' >/dev/null; then
        echo "[ERROR] Failed to add agent to room" > "$temp_output_file"
        api_call DELETE "/rooms/$room_id" "" "$token" >/dev/null
        return 1
    fi

    # Escape question for JSON
    local question_json=$(echo "$question" | jq -Rs .)

    # Send question as user message
    local send_response=$(api_call POST "/rooms/$room_id/messages/send" \
        "{\"content\":$question_json,\"role\":\"user\",\"participant_type\":\"user\"}" \
        "$token")

    if ! echo "$send_response" | jq -e '.id' >/dev/null; then
        echo "[ERROR] Failed to send question" > "$temp_output_file"
        api_call DELETE "/rooms/$room_id" "" "$token" >/dev/null
        return 1
    fi

    # Get the message ID of the question we just sent
    local sent_message_id=$(echo "$send_response" | jq -r '.id')

    # Poll for agent response (up to 120 seconds)
    local wait_count=0
    local max_wait=180  # 60 * 2 seconds = 120 seconds
    local agent_response=""

    while [ $wait_count -lt $max_wait ]; do
        sleep 2

        # Poll for new messages since our question
        local messages=$(api_call GET "/rooms/$room_id/messages/poll?since_id=$sent_message_id" "" "$token")

        # Check if we got new messages
        local msg_count=$(echo "$messages" | jq 'length')

        if [ "$msg_count" -gt 0 ]; then
            agent_response=$(echo "$messages" | jq -r '.[0].content // empty')
            agent_thinking=$(echo "$messages" | jq -r '.[0].thinking // empty')
            agent_anthropic_calls=$(echo "$messages" | jq -c '.[0].anthropic_calls // empty')

            if [ -n "$agent_response" ] && [ "$agent_response" != "null" ]; then
                break
            fi
        fi

        ((wait_count++))
    done

    # Write result to temp file
    {
        echo "Q_NUM:${q_num}"
        echo "QUESTION:${question}"
        if [ -n "$agent_thinking" ] && [ "$agent_thinking" != "null" ]; then
            echo "THINKING:${agent_thinking}"
        fi
        if [ -n "$agent_anthropic_calls" ] && [ "$agent_anthropic_calls" != "null" ] && [ "$agent_anthropic_calls" != "[]" ]; then
            echo "ANTHROPIC_CALLS:${agent_anthropic_calls}"
        fi
        if [ -n "$agent_response" ] && [ "$agent_response" != "null" ]; then
            echo "ANSWER:${agent_response}"
        else
            echo "ANSWER:[NO RESPONSE AFTER 120s]"
        fi
    } > "$temp_output_file"

    # Delete the room (cleanup)
    api_call DELETE "/rooms/$room_id" "" "$token" >/dev/null
}

# Function to test a single agent with parallel questions
test_agent() {
    local agent_name=$1
    local questions_file=$2
    local max_questions=$3
    local token=$4
    local output_file=$5

    log "${GREEN}[${agent_name}] Starting test${NC}" "$output_file"

    # Get agent ID once
    local all_agents=$(api_call GET "/agents" "" "$token")
    local agent_id=$(echo "$all_agents" | jq -r ".[] | select(.name==\"$agent_name\") | .id // empty")

    if [ -z "$agent_id" ]; then
        log "${RED}[${agent_name}] Agent not found${NC}" "$output_file"
        return 1
    fi

    # Extract questions
    readarray -t questions < <(extract_questions "$questions_file" "$max_questions")
    local total_questions=${#questions[@]}

    log "\n${BLUE}[${agent_name}] Asking ${total_questions} questions in parallel...${NC}\n" "$output_file"

    # Create temp directory for results
    local temp_dir=$(mktemp -d)
    local pids=()

    # Launch all questions in parallel
    local q_num=1
    for question in "${questions[@]}"; do
        local temp_output="${temp_dir}/q${q_num}.txt"

        # Export necessary functions and variables for subshell
        export -f api_call test_single_question
        export API_BASE BATCH_ID CHECK_ANT

        # Launch question test in background
        test_single_question "$agent_name" "$agent_id" "$q_num" "$total_questions" "$question" "$token" "$temp_output" &
        pids+=($!)

        # Stagger starts slightly to avoid API overload
        sleep 0.5

        ((q_num++))
    done

    # Wait for all questions to complete
    log "${BLUE}[${agent_name}] Waiting for ${total_questions} parallel questions to complete...${NC}" "$output_file"
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null
    done

    # Collect and display results in order
    log "\n${BLUE}[${agent_name}] Results:${NC}\n" "$output_file"

    for ((i=1; i<=total_questions; i++)); do
        local temp_output="${temp_dir}/q${i}.txt"

        log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}" "$output_file"
        log "${GREEN}[${agent_name}] Question ${i}/${total_questions}${NC}" "$output_file"
        log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n" "$output_file"

        if [ -f "$temp_output" ]; then
            # Check for error
            if grep -q "^\[ERROR\]" "$temp_output"; then
                log "${RED}$(cat "$temp_output")${NC}\n" "$output_file"
            else
                # Parse structured output
                local q_text=$(grep "^QUESTION:" "$temp_output" | sed 's/^QUESTION://')
                # Extract thinking (everything between THINKING: and next section)
                local t_text=""
                if grep -q "^THINKING:" "$temp_output"; then
                    t_text=$(sed -n '/^THINKING:/,/^\(ANTHROPIC_CALLS:\|ANSWER:\)/{ /^\(ANTHROPIC_CALLS:\|ANSWER:\)/d; s/^THINKING://; p; }' "$temp_output")
                fi
                # Extract anthropic_calls
                local ant_text=""
                if grep -q "^ANTHROPIC_CALLS:" "$temp_output"; then
                    ant_text=$(grep "^ANTHROPIC_CALLS:" "$temp_output" | sed 's/^ANTHROPIC_CALLS://')
                fi
                # Read everything from ANSWER: line to end of file (handles multiline responses)
                local a_text=$(sed -n '/^ANSWER:/,$p' "$temp_output" | sed '1s/^ANSWER://')

                log "Q: ${q_text}\n" "$output_file"
                # Show thinking if enabled and present
                if [ "$SHOW_THINKING" = "true" ] && [ -n "$t_text" ]; then
                    log "${DIM}${CYAN}💭 Thinking:${NC}" "$output_file"
                    log "${DIM}${t_text}${NC}\n" "$output_file"
                fi
                # Show anthropic calls if CHECK_ANT=1 and present
                if [ "$CHECK_ANT" = "1" ] && [ -n "$ant_text" ]; then
                    log "${YELLOW}🔒 mcp__guidelines__anthropic called:${NC}" "$output_file"
                    log "${YELLOW}   ${ant_text}${NC}\n" "$output_file"
                fi
                if [[ "$a_text" == "[NO RESPONSE"* ]]; then
                    log "${RED}A: ${a_text}${NC}\n" "$output_file"
                else
                    log "${BLUE}A:${NC} ${a_text}\n" "$output_file"
                fi
            fi
        else
            log "${RED}[${agent_name}] No result file for Q${i}${NC}\n" "$output_file"
        fi
    done

    # Cleanup temp directory
    rm -rf "$temp_dir"

    log "\n${GREEN}[${agent_name}] Test completed!${NC}\n" "$output_file"
}

# Main script
qecho "${BLUE}=== Agent Question Testing ===${NC}"
qecho "${BLUE}Batch ID: ${BATCH_ID}${NC}"
qecho "${BLUE}Testing ${#AGENTS_TO_TEST[@]} agents in parallel: ${AGENTS_TO_TEST[*]}${NC}"
qecho "${BLUE}Questions per agent: ${QUESTIONS_PER_AGENT}${NC}"

# Show info about CHECK_ANT mode
if [ "$CHECK_ANT" = "1" ]; then
    qecho "${CYAN}CHECK_ANT=1: Will show mcp__guidelines__anthropic tool calls${NC}"
fi
qecho ""

# Authenticate
qecho "${BLUE}Authenticating...${NC}"
JWT_TOKEN=$(authenticate)
qecho "${GREEN}Authenticated successfully${NC}"
qecho ""

# Launch tests for agents in parallel
qecho "${BLUE}Starting agent tests...${NC}"
qecho ""

agent_count=0
for agent_name in "${AGENTS_TO_TEST[@]}"; do
    # Find agent directory (could be in agents/ directly or in a group subdirectory)
    agent_dir=""
    if [ -f "agents/${agent_name}/in_a_nutshell.md" ]; then
        agent_dir="agents/${agent_name}"
    else
        # Search in group subdirectories
        agent_dir=$(find agents -type f -path "*/${agent_name}/in_a_nutshell.md" -exec dirname {} \; | head -1)
    fi

    if [ -z "$agent_dir" ]; then
        qecho "${YELLOW}Warning: Agent '${agent_name}' not found in agents/, skipping${NC}"
        continue
    fi

    # Check if question file exists
    questions_file="agent_questions/${agent_name}.md"
    if [ ! -f "$questions_file" ]; then
        qecho "${YELLOW}Warning: Questions file '${questions_file}' not found, skipping${NC}"
        continue
    fi

    # Output file
    output_file="test_${agent_name}_${BATCH_ID}.txt"

    # Launch agent test in background
    test_agent "$agent_name" "$questions_file" "$QUESTIONS_PER_AGENT" "$JWT_TOKEN" "$output_file" &

    # Stagger starts
    sleep 2

    ((agent_count++))
done

if [ $agent_count -eq 0 ]; then
    qecho "${RED}No valid agents found to test${NC}"
    exit 1
fi

qecho ""
qecho "${BLUE}=== All ${agent_count} agent tests running in parallel ===${NC}"
qecho "${BLUE}Waiting for completion...${NC}"
qecho ""

# Wait for all background jobs
wait

qecho ""
qecho "${GREEN}=== All tests completed! ===${NC}"
qecho ""
qecho "${BLUE}Generated transcripts:${NC}"
if [ "$QUIET" != "true" ]; then
    ls -lh test_*_${BATCH_ID}.txt 2>/dev/null || echo "No files found"
fi
