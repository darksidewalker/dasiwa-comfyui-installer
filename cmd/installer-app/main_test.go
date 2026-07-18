package main

import (
	"strings"
	"testing"
	"time"
)

func TestCloseAfterGraceShutsDownWithoutReconnect(t *testing.T) {
	s := &server{logs: newBroker(), closeSignalSeq: 1}
	signaledAt := time.Now()

	s.closeAfterGrace(1, signaledAt, time.Millisecond)

	if !eventuallyLogContains(s.logs, "Browser tab closed; shutting down installer.", 100*time.Millisecond) {
		t.Fatalf("expected shutdown log after browser close grace")
	}
}

func TestCloseAfterGraceKeepsServerAliveAfterReconnect(t *testing.T) {
	s := &server{logs: newBroker(), closeSignalSeq: 1}
	signaledAt := time.Now()
	s.heartbeatMu.Lock()
	s.heartbeatSeen = true
	s.lastHeartbeat = signaledAt.Add(time.Millisecond)
	s.heartbeatMu.Unlock()

	s.closeAfterGrace(1, signaledAt, time.Millisecond)

	if eventuallyLogContains(s.logs, "Browser tab closed", 25*time.Millisecond) {
		t.Fatalf("unexpected shutdown log after heartbeat reconnect")
	}
}

func TestBrokerSubscribeReplaysLargeHistoryWithoutBlocking(t *testing.T) {
	logs := newBroker()
	for i := 0; i < 200; i++ {
		logs.send("previous log line")
	}

	done := make(chan struct{})
	var history []string
	var ch chan string
	go func() {
		history, ch = logs.subscribe()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(100 * time.Millisecond):
		t.Fatal("subscribe blocked while replaying history")
	}
	defer logs.remove(ch)
	if len(history) != 200 {
		t.Fatalf("replayed history has %d lines, want 200", len(history))
	}
}

func eventuallyLogContains(logs *broker, needle string, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for {
		logs.mu.Lock()
		for _, line := range logs.history {
			if strings.Contains(line, needle) {
				logs.mu.Unlock()
				return true
			}
		}
		logs.mu.Unlock()
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(time.Millisecond)
	}
}
