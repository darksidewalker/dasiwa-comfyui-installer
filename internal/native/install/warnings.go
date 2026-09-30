package install

import "strings"

// WarningsError means the core install and launchers finished, but optional
// components or node dependencies remain incomplete.
type WarningsError struct {
	Details []string
}

func (w *WarningsError) Error() string {
	return strings.Join(w.Details, "; ")
}
