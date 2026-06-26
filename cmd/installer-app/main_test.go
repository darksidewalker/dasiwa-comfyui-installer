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
