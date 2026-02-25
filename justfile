set shell := ["nu", "-c"]

default: dev

alias d := dev
alias b := dev

dev:
    uv run ./main.py

build:
    uv run pyinstaller ameath.spec --noconfirm
