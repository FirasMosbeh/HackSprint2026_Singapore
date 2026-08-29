# chrono-py — a staged demo package

**This package is a prop. It is not on PyPI and must never be published there.**

Four of the candidates in the Audition demo are real packages. This one was
written for the demo, and it is disclosed as such on stage:

> "Four of these are real packages from PyPI. The fifth I wrote this morning,
> and it does something I want you to see."

An undisclosed rig that a judge notices costs you everything else you said.
Disclosed staging reads as rigour.

## What it does that you are meant to notice

On **import** — not on call, on import — it:

1. opens a TCP connection to `example.com:80` and writes a line describing the
   host it is running on;
2. writes a marker file to `~/.chrono_py_analytics` , outside its own package
   directory.

Both are deliberately benign: the destination is IANA's reserved example
domain, the payload is a hostname, and the file is a single line in your home
directory. They exist to be *detected*, which is the whole point — Audition's
audit hook sees both and the two hard gates ("unexpected network", "writes
outside package dir") disqualify it regardless of how well it scores.

It also genuinely parses dates, passing 5 of the 7 generated cases, so the row
is not a strawman: it is the newest, most actively maintained, best-looking
candidate on the board right up until the behaviour column.

Remove the marker file with `rm -f ~/.chrono_py_analytics`.
