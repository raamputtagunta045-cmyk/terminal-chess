---
name: Bug report
about: Something is wrong with the rules, the engine, or the interface
labels: bug
---

**What happened**

**What you expected instead**

**Position**

The FEN, if you have it. `fen` prints it from inside the game, and it is by far
the most useful single thing you can include:

```
paste the FEN here
```

**Moves played**

The output of the `history` command, or the PGN from `save`.

**Environment**

- Python version:
- Operating system:
- Difficulty level, if the engine is involved:

**A note on engine strength**

"The engine played a bad move" is usually not a bug -- it searches to a limited
depth and will miss things beyond it. It *is* a bug if the engine played an
illegal move, crashed, ignored a forced mate it had time to see, or accepted a
draw in a won position.
