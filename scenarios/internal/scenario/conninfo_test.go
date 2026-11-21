package scenario

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestConnectionInfo(t *testing.T) {
	assert.Equal(t, "http://localhost:32768", ConnectionInfo("http", 32768))
	assert.Equal(t, "nc localhost 32768", ConnectionInfo("tcp", 32768))
}
