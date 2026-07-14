import { describe, it, expect, beforeEach, beforeAll, afterAll, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import type { Message } from '../types'
import { setApiKey } from '../services'
import { usePolling } from './usePolling'

// Stand in for the real SSE hook so tests control connection state and can
// deliver a new_message without a live EventSource.
const sse = vi.hoisted(() => ({
  isConnected: false,
  streamingAgents: new Map<number, unknown>(),
  error: null as string | null,
  onNewMessage: undefined as ((message: Message) => void) | undefined,
}))

vi.mock('./useSSE', () => ({
  useSSE: (_roomId: number | null, onNewMessage?: (message: Message) => void) => {
    sse.onNewMessage = onNewMessage
    return {
      isConnected: sse.isConnected,
      streamingAgents: sse.streamingAgents,
      error: sse.error,
    }
  },
}))

global.fetch = vi.fn()

/** Shape apiClient actually consumes: it reads response.text(), not response.json(). */
const jsonResponse = (data: unknown) => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  text: async () => JSON.stringify(data),
  json: async () => data,
})

const errorResponse = () => ({
  ok: false,
  status: 404,
  statusText: 'Not Found',
  text: async () => '',
  json: async () => ({ detail: 'Not Found' }),
})

const mockFetch = () => global.fetch as unknown as ReturnType<typeof vi.fn>

/** Calls to a specific endpoint, ignoring the polling/chatting-agent chatter. */
const callsTo = (suffix: string) =>
  mockFetch().mock.calls.filter((call: unknown[]) => String(call[0]).endsWith(suffix))

const originalConsoleError = console.error
beforeAll(() => {
  console.error = vi.fn()
})

afterAll(() => {
  console.error = originalConsoleError
})

describe('usePolling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setApiKey('test-api-key')
    sse.isConnected = false
    sse.streamingAgents = new Map()
    sse.onNewMessage = undefined
  })

  it('should initialize with empty messages and disconnected state', () => {
    const { result } = renderHook(() => usePolling(null))

    expect(result.current.messages).toEqual([])
    expect(result.current.isConnected).toBe(false)
  })

  it('should fetch all messages on initial load when roomId is provided', async () => {
    const mockMessages = [
      { id: 1, content: 'Hello', role: 'user', timestamp: '2024-01-01' },
      { id: 2, content: 'Hi', role: 'assistant', timestamp: '2024-01-02' },
    ]

    mockFetch().mockResolvedValue(jsonResponse(mockMessages))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/rooms/1/messages'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-API-Key': 'test-api-key',
            'ngrok-skip-browser-warning': 'true',
          }),
        })
      )
    })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(2)
    })
  })

  it('should set isConnected to true on successful message fetch', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should set isConnected to false on failed message fetch', async () => {
    mockFetch().mockResolvedValue(errorResponse())

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should handle network errors gracefully', async () => {
    mockFetch().mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should send message with correct headers and body', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    await act(async () => {
      await result.current.sendMessage('Test message')
    })

    const sendCall = callsTo('/messages/send')[0]
    expect(sendCall).toBeDefined()
    expect(sendCall[1]).toMatchObject({
      method: 'POST',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-API-Key': 'test-api-key',
      }),
    })
    expect(JSON.parse((sendCall[1] as RequestInit).body as string)).toMatchObject({
      content: 'Test message',
      role: 'user',
    })
  })

  it('should send message with optional parameters', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    await act(async () => {
      await result.current.sendMessage(
        'Test',
        'situation_builder',
        'Builder',
        [{ data: 'base64data', media_type: 'image/png' }]
      )
    })

    const sendCall = callsTo('/messages/send')[0]
    expect(sendCall).toBeDefined()
    expect(JSON.parse((sendCall[1] as RequestInit).body as string)).toMatchObject({
      content: 'Test',
      role: 'user',
      participant_type: 'situation_builder',
      participant_name: 'Builder',
      images: [{ data: 'base64data', media_type: 'image/png' }],
    })
  })

  it('should reset messages on resetMessages call', async () => {
    const initialMessages = [
      { id: 1, content: 'Hello', role: 'user', timestamp: '2024-01-01' },
    ]

    mockFetch().mockResolvedValue(jsonResponse(initialMessages))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
    })

    mockFetch().mockResolvedValue(jsonResponse([]))

    await act(async () => {
      await result.current.resetMessages()
    })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(0)
    })
  })

  it('should clear messages when roomId changes', async () => {
    const room1Messages = [
      { id: 1, content: 'Room 1', role: 'user', timestamp: '2024-01-01' },
    ]
    const room2Messages = [
      { id: 2, content: 'Room 2', role: 'user', timestamp: '2024-01-02' },
    ]

    mockFetch().mockImplementation((url: string) =>
      Promise.resolve(
        url.includes('/rooms/1/messages') && !url.includes('poll')
          ? jsonResponse(room1Messages)
          : url.includes('/rooms/2/messages') && !url.includes('poll')
            ? jsonResponse(room2Messages)
            : jsonResponse([])
      )
    )

    const { result, rerender } = renderHook(({ roomId }) => usePolling(roomId), {
      initialProps: { roomId: 1 },
    })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toBe('Room 1')
    })

    rerender({ roomId: 2 })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toBe('Room 2')
    })
  })

  it('should not make API calls when roomId is null', () => {
    renderHook(() => usePolling(null))

    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('should expose setMessages for external updates', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    const newMessage = {
      id: 3, content: 'External', role: 'user', timestamp: '2024-01-03', agent_id: null,
    }

    act(() => {
      result.current.setMessages((prev) => [...prev, newMessage as unknown as Message])
    })

    await waitFor(() => {
      expect(result.current.messages).toContainEqual(newMessage)
    })
  })

  // Regression: SSE connecting used to re-run the setup effect, which calls
  // setMessages([]) — blanking and refetching the transcript on every room open.
  it('should not clear or refetch messages when SSE connects', async () => {
    const loaded = [
      { id: 1, content: 'Hello', role: 'user', timestamp: '2024-01-01' },
    ]
    mockFetch().mockResolvedValue(jsonResponse(loaded))

    const { result, rerender } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
    })
    expect(callsTo('/rooms/1/messages')).toHaveLength(1)

    // SSE finishes connecting a moment after the initial load
    sse.isConnected = true
    rerender()

    await waitFor(() => {
      expect(result.current.sseConnected).toBe(true)
    })

    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].content).toBe('Hello')
    expect(callsTo('/rooms/1/messages')).toHaveLength(1)
  })

  // Regression: finalized messages arrive over SSE, not just on the 5s poll tick.
  it('should append a message delivered via SSE new_message', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
    expect(sse.onNewMessage).toBeDefined()

    const incoming = {
      id: 7, room_id: 1, agent_id: 2, content: 'From SSE',
      role: 'assistant', timestamp: '2024-01-04',
    } as unknown as Message

    act(() => sse.onNewMessage!(incoming))

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toBe('From SSE')
    })

    // A redelivery (or a poll that races it) must not duplicate the message
    act(() => sse.onNewMessage!(incoming))

    expect(result.current.messages).toHaveLength(1)
  })

  it('should drop the chatting indicator for the agent whose message arrived', async () => {
    mockFetch().mockResolvedValue(jsonResponse([]))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    act(() => {
      result.current.setMessages([
        { id: 'chatting_2', agent_id: 2, content: 'typ', role: 'assistant', is_chatting: true } as unknown as Message,
        { id: 'chatting_3', agent_id: 3, content: 'typ', role: 'assistant', is_chatting: true } as unknown as Message,
      ])
    })

    act(() => sse.onNewMessage!({
      id: 9, room_id: 1, agent_id: 2, content: 'done', role: 'assistant', timestamp: '2024-01-05',
    } as unknown as Message))

    await waitFor(() => {
      const ids = result.current.messages.map(m => m.id)
      expect(ids).toEqual([9, 'chatting_3'])
    })
  })
})
