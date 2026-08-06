# Test-01

This repository contains a small backend worker launcher and a Harbor task
that asks an agent to make the launcher portable across POSIX `/bin/sh`
implementations while preserving arguments, signals, and exit status.

The source used to build the task environment lives in `project/backend/`.
The Harbor package lives in `harbor-task/`.
