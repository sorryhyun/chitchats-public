import { describe, it, expect, beforeEach, beforeAll, afterAll, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { usePolling } from './usePolling'

// Mock the api module
vi.mock('../utils/api', () => ({
  getApiKey: vi.fn(() => 'test-api-key'),
}))

// Mock fetch
global.fetch = vi.fn()

// Suppress console errors in tests
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

    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => mockMessages,
    })

    renderHook(() => usePolling(1))

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
  })

  it('should set isConnected to true on successful message fetch', async () => {
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should set isConnected to false on failed message fetch', async () => {
    ;(global.fetch as any).mockResolvedValue({
      ok: false,
      statusText: 'Not Found',
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should handle network errors gracefully', async () => {
    ;(global.fetch as any).mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should send message with correct headers and body', async () => {
    // Mock initial fetch
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })

    // Mock send message
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })

    // Mock ongoing polling
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    result.current.sendMessage('Test message')

    await waitFor(() => {
      const sendCall = (global.fetch as any).mock.calls.find((call: any[]) =>
        call[0].includes('/messages/send')
      )
      expect(sendCall).toBeDefined()
      expect(sendCall[1]).toMatchObject({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-API-Key': 'test-api-key',
        }),
      })
      expect(JSON.parse(sendCall[1].body)).toMatchObject({
        content: 'Test message',
        role: 'user',
      })
    })
  })

  it('should send message with optional parameters', async () => {
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    result.current.sendMessage(
      'Test',
      'situation_builder',
      'Builder',
      [{ data: 'base64data', media_type: 'image/png' }]
    )

    await waitFor(() => {
      const sendCall = (global.fetch as any).mock.calls.find((call: any[]) =>
        call[0].includes('/messages/send')
      )
      expect(sendCall).toBeDefined()
      const body = JSON.parse(sendCall[1].body)
      expect(body).toMatchObject({
        content: 'Test',
        role: 'user',
        participant_type: 'situation_builder',
        participant_name: 'Builder',
        images: [{ data: 'base64data', media_type: 'image/png' }],
      })
    })
  })

  it('should reset messages on resetMessages call', async () => {
    const initialMessages = [
      { id: 1, content: 'Hello', role: 'user', timestamp: '2024-01-01' },
    ]

    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => initialMessages,
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
    })

    // Mock the refetch after reset
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })

    // Mock ongoing polling
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    await result.current.resetMessages()

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

    // First room fetch
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => room1Messages,
    })

    // Mock ongoing polling for room 1
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result, rerender } = renderHook(({ roomId }) => usePolling(roomId), {
      initialProps: { roomId: 1 },
    })

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(1)
      expect(result.current.messages[0].content).toBe('Room 1')
    })

    // Second room fetch
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => room2Messages,
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
    ;(global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { result } = renderHook(() => usePolling(1))

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    const newMessages = [
      { id: 3, content: 'External', role: 'user', timestamp: '2024-01-03', agent_id: null },
    ]

    // Use act to wrap state update
    result.current.setMessages((prev) => [...prev, ...newMessages])

    await waitFor(() => {
      expect(result.current.messages).toContainEqual(newMessages[0])
    })
  })
})
