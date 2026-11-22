package scenario

import "fmt"

func ConnectionInfo(protocol string, hostPort int) string {
	if protocol == "tcp" {
		return fmt.Sprintf("nc localhost %d", hostPort)
	}
	return fmt.Sprintf("http://localhost:%d", hostPort)
}
