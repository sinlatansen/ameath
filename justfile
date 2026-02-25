set shell := ["nu", "-c"]

default: dev

alias d := dev
alias b := build

dev:
    uv run ./main.py

build:
    uv run pyinstaller ameath.spec --noconfirm
