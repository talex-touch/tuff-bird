# Security

Please report a vulnerability through GitHub's
[private vulnerability reporting](https://github.com/talex-touch/tuff-bird/security/advisories/new)
rather than in a public issue.

The board has no authentication. It listens on 127.0.0.1 by default, and anyone who can
reach its port can read every log, config and printed line in the directory it serves.
Reaching it from another machine through an SSH tunnel keeps it that way; setting
`TUFFBIRD_BOARD_HOST` to another address does not.
