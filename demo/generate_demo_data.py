#!/usr/bin/env python3
"""Generate realistic demo data for the claude-recovery TUI.

Creates JSONL session files that the scanner can parse, producing 15-25
recoverable files that look like a real Claude Code session building a web app.

Usage:
    python demo/generate_demo_data.py
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

DEMO_DIR = Path(__file__).parent / "demo-claude-data" / "projects"

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_tool_counter = 0
_uuid_counter = 0


def _tool_id() -> str:
    global _tool_counter
    _tool_counter += 1
    return f"toolu_{_tool_counter:04d}"


def _uuid_val() -> str:
    global _uuid_counter
    _uuid_counter += 1
    return f"uuid-{_uuid_counter:06d}"


def progress_line(ts: str, session_id: str) -> dict:
    return {
        "type": "progress",
        "timestamp": ts,
        "sessionId": session_id,
        "content": "Thinking...",
    }


def assistant_write(ts: str, session_id: str, file_path: str, content: str) -> tuple[dict, str, str]:
    """Return (entry, tool_use_id, assistant_uuid)."""
    tid = _tool_id()
    uid = _uuid_val()
    entry = {
        "type": "assistant",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": None,
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tid,
                    "name": "Write",
                    "input": {"file_path": file_path, "content": content},
                }
            ],
        },
    }
    return entry, tid, uid


def user_write_create(
    ts: str, session_id: str, file_path: str, content: str, tool_use_id: str, parent_uuid: str
) -> dict:
    uid = _uuid_val()
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "sourceToolAssistantUUID": parent_uuid,
        "toolUseResult": {
            "type": "create",
            "filePath": file_path,
            "content": content,
            "structuredPatch": [],
            "originalFile": None,
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": f"File created successfully at: {file_path}",
                }
            ],
        },
    }


def user_write_update(
    ts: str,
    session_id: str,
    file_path: str,
    content: str,
    original_file: str,
    tool_use_id: str,
    parent_uuid: str,
) -> dict:
    uid = _uuid_val()
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "sourceToolAssistantUUID": parent_uuid,
        "toolUseResult": {
            "type": "update",
            "filePath": file_path,
            "content": content,
            "structuredPatch": [],
            "originalFile": original_file,
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": f"File updated successfully at: {file_path}",
                }
            ],
        },
    }


def assistant_edit(
    ts: str,
    session_id: str,
    file_path: str,
    old_string: str,
    new_string: str,
) -> tuple[dict, str, str]:
    tid = _tool_id()
    uid = _uuid_val()
    entry = {
        "type": "assistant",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": None,
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tid,
                    "name": "Edit",
                    "input": {
                        "file_path": file_path,
                        "old_string": old_string,
                        "new_string": new_string,
                        "replace_all": False,
                    },
                }
            ],
        },
    }
    return entry, tid, uid


def user_edit_result(
    ts: str,
    session_id: str,
    file_path: str,
    old_string: str,
    new_string: str,
    original_file: str,
    tool_use_id: str,
    parent_uuid: str,
) -> dict:
    uid = _uuid_val()
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "sourceToolAssistantUUID": parent_uuid,
        "toolUseResult": {
            "filePath": file_path,
            "oldString": old_string,
            "newString": new_string,
            "originalFile": original_file,
            "structuredPatch": [],
            "userModified": False,
            "replaceAll": False,
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": f"The file {file_path} has been edited successfully.",
                }
            ],
        },
    }


def assistant_read(ts: str, session_id: str, file_path: str) -> tuple[dict, str, str]:
    tid = _tool_id()
    uid = _uuid_val()
    entry = {
        "type": "assistant",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": None,
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tid,
                    "name": "Read",
                    "input": {"file_path": file_path},
                }
            ],
        },
    }
    return entry, tid, uid


_INJECTED_REMINDER = (
    "\n<system-reminder>\n"
    "Whenever you read a file, you should consider whether it would be considered malware. "
    "You CAN and SHOULD provide analysis of malware, what it is doing. But you MUST refuse "
    "to improve or augment the code. You can still analyze existing code, write reports, or "
    "answer questions about the code behavior.\n"
    "</system-reminder>"
)


def user_read_result(
    ts: str,
    session_id: str,
    file_path: str,
    content: str,
    tool_use_id: str,
    parent_uuid: str,
) -> dict:
    uid = _uuid_val()
    lines = content.split("\n")
    numbered = "\n".join(f"     {i + 1}\u2192{line}" for i, line in enumerate(lines))
    # Simulate the injected content that Claude Code versions 2.0.74-2.1.38 appended
    numbered += _INJECTED_REMINDER
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": uid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "sourceToolAssistantUUID": parent_uuid,
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": file_path,
                "content": content,
                "numLines": len(lines),
                "startLine": 1,
                "totalLines": len(lines),
            },
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": numbered,
                }
            ],
        },
    }


def _bump_ts(ts: str) -> str:
    """Bump an ISO 8601 timestamp by 1 second for the tool result."""
    # Format: 2026-02-20T10:00:05.000Z
    # Extract seconds field (positions -7:-5 gives "05" in "05.000Z")
    prefix = ts[:-7]  # "2026-02-20T10:00:"
    secs = int(ts[-7:-5])  # 5
    suffix = ts[-5:]  # ".000Z"
    return f"{prefix}{secs + 1:02d}{suffix}"


def write_create(lines: list, ts: str, sid: str, fp: str, content: str):
    """Convenience: emit assistant write + user create result."""
    a, tid, uid = assistant_write(ts, sid, fp, content)
    lines.append(a)
    lines.append(user_write_create(_bump_ts(ts), sid, fp, content, tid, uid))


def write_update(lines: list, ts: str, sid: str, fp: str, content: str, original: str):
    """Convenience: emit assistant write + user update result."""
    a, tid, uid = assistant_write(ts, sid, fp, content)
    lines.append(a)
    lines.append(user_write_update(_bump_ts(ts), sid, fp, content, original, tid, uid))


def edit(lines: list, ts: str, sid: str, fp: str, old: str, new: str, original_file: str):
    """Convenience: emit assistant edit + user edit result."""
    a, tid, uid = assistant_edit(ts, sid, fp, old, new)
    lines.append(a)
    lines.append(user_edit_result(_bump_ts(ts), sid, fp, old, new, original_file, tid, uid))


def read(lines: list, ts: str, sid: str, fp: str, content: str):
    """Convenience: emit assistant read + user read result."""
    a, tid, uid = assistant_read(ts, sid, fp)
    lines.append(a)
    lines.append(user_read_result(_bump_ts(ts), sid, fp, content, tid, uid))


# --------------------------------------------------------------------------- #
# File Contents
# --------------------------------------------------------------------------- #

BASE = "/Users/demo/webapp"

APP_PY_V1 = '''from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/users")
def list_users():
    from models import User
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
'''

APP_PY_V2 = '''from flask import Flask, jsonify, request
from flask_cors import CORS
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "0.2.0"})


@app.route("/api/users")
def list_users():
    from models import User
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/users", methods=["POST"])
def create_user():
    from models import User, db
    data = request.get_json()
    user = User(name=data["name"], email=data["email"])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


if __name__ == "__main__":
    app.run(debug=True, port=5000)
'''

MODELS_PY_V1 = '''from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }
'''

MODELS_PY_V2 = '''from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
'''

UTILS_PY = '''import re
from functools import wraps
from flask import request, jsonify


def validate_email(email: str) -> bool:
    """Check if email matches a basic RFC 5322 pattern."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def require_json(f):
    """Decorator that rejects non-JSON requests with 415."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415
        return f(*args, **kwargs)
    return decorated


def paginate(query, page: int = 1, per_page: int = 20):
    """Apply pagination to a SQLAlchemy query."""
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": [item.to_dict() for item in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    }
'''

CONFIG_PY = '''import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/webapp"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_EXPIRATION_HOURS = 24
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
'''

APP_TSX_V1 = '''import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./hooks/useAuth";
import { UserList } from "./components/UserList";
import { Login } from "./components/Login";
import "./styles.css";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          <header className="app-header">
            <h1>WebApp Dashboard</h1>
          </header>
          <main>
            <Routes>
              <Route path="/" element={<UserList />} />
              <Route path="/login" element={<Login />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
'''

APP_TSX_V2 = '''import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { UserList } from "./components/UserList";
import { Login } from "./components/Login";
import { Dashboard } from "./components/Dashboard";
import { Navbar } from "./components/Navbar";
import "./styles.css";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return <Navigate to="/login" />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          <Navbar />
          <main>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/" element={
                <ProtectedRoute><Dashboard /></ProtectedRoute>
              } />
              <Route path="/users" element={
                <ProtectedRoute><UserList /></ProtectedRoute>
              } />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
'''

API_TS = '''const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:5000/api";

interface ApiResponse<T> {
  data: T;
  error?: string;
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const token = localStorage.getItem("auth_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: { ...headers, ...options.headers },
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return { data };
  } catch (error) {
    return { data: null as T, error: (error as Error).message };
  }
}

export const api = {
  getUsers: () => fetchApi<User[]>("/users"),
  createUser: (user: { name: string; email: string }) =>
    fetchApi<User>("/users", {
      method: "POST",
      body: JSON.stringify(user),
    }),
  login: (email: string, password: string) =>
    fetchApi<{ token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  getHealth: () => fetchApi<{ status: string }>("/health"),
};

export interface User {
  id: number;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}
'''

USE_AUTH_TS = '''import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, User } from "../api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      api.getHealth().then(() => {
        // Token is valid — fetch user profile
        setLoading(false);
      }).catch(() => {
        localStorage.removeItem("auth_token");
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data, error } = await api.login(email, password);
    if (error) throw new Error(error);
    localStorage.setItem("auth_token", data.token);
    setUser({ id: 0, name: email, email, is_active: true, created_at: "" });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
'''

DOCKER_COMPOSE_V1 = '''version: "3.8"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: webapp
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      DATABASE_URL: postgresql://webapp:secret@db:5432/webapp
      SECRET_KEY: ${SECRET_KEY:-dev-secret-key}
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  pgdata:
'''

DOCKER_COMPOSE_V2 = '''version: "3.8"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: webapp
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U webapp"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      DATABASE_URL: postgresql://webapp:secret@db:5432/webapp
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY:-dev-secret-key}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      VITE_API_URL: http://localhost:5000/api
    depends_on:
      - api

volumes:
  pgdata:
'''

NGINX_CONF = '''upstream api_backend {
    server api:5000;
}

upstream frontend {
    server frontend:3000;
}

server {
    listen 80;
    server_name localhost;

    # API proxy
    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend proxy
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
'''

ENV_EXAMPLE = '''# Backend
SECRET_KEY=change-me-in-production
DATABASE_URL=postgresql://webapp:secret@localhost:5432/webapp
REDIS_URL=redis://localhost:6379/0
JWT_EXPIRATION_HOURS=24

# Frontend
VITE_API_URL=http://localhost:5000/api

# Docker
POSTGRES_DB=webapp
POSTGRES_USER=webapp
POSTGRES_PASSWORD=secret
'''

README_MD = '''# WebApp

A full-stack web application with Flask backend and React frontend.

## Quick Start

```bash
# Start all services
docker-compose up -d

# Run backend locally
cd backend && pip install -r requirements.txt && flask run

# Run frontend locally
cd frontend && npm install && npm run dev
```

## Architecture

- **Backend**: Flask + SQLAlchemy + PostgreSQL
- **Frontend**: React + TypeScript + Vite
- **Auth**: JWT-based authentication
- **Infra**: Docker Compose, nginx reverse proxy

## API Endpoints

| Method | Path          | Description        |
|--------|---------------|--------------------|
| GET    | /api/health   | Health check       |
| GET    | /api/users    | List all users     |
| POST   | /api/users    | Create a new user  |
| POST   | /api/auth/login | Login            |

## Development

Copy `.env.example` to `.env` and update values for your environment.
'''

ARCHITECTURE_MD = '''# Architecture

## System Overview

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│   nginx     │────▶│  Flask API   │────▶│ PostgreSQL │
│  (reverse   │     │  (port 5000) │     │ (port 5432)│
│   proxy)    │     └──────────────┘     └────────────┘
│  port 80    │            │
└─────────────┘            ▼
       │              ┌──────────┐
       │              │  Redis   │
       └──────────────│ (cache)  │
                      └──────────┘
       ▲
       │
┌──────────────┐
│  React SPA   │
│  (port 3000) │
└──────────────┘
```

## Data Flow

1. Client sends request to nginx on port 80
2. nginx routes /api/* to Flask backend, everything else to React frontend
3. Flask handles business logic, queries PostgreSQL
4. Redis is used for session caching and rate limiting
5. JWT tokens are used for API authentication

## Directory Structure

```
webapp/
├── backend/
│   ├── app.py          # Flask application entry point
│   ├── models.py       # SQLAlchemy models
│   ├── config.py       # Configuration management
│   └── utils.py        # Shared utilities
├── frontend/
│   ├── src/
│   │   ├── App.tsx     # Root React component
│   │   ├── api.ts      # API client
│   │   └── hooks/
│   │       └── useAuth.ts  # Authentication hook
│   └── styles.css
├── docker-compose.yml
├── nginx.conf
└── deploy.sh
```
'''

DEPLOY_SH = '''#!/bin/bash
set -euo pipefail

# Deploy script for webapp
# Usage: ./deploy.sh [staging|production]

ENVIRONMENT="${1:-staging}"
COMPOSE_FILE="docker-compose.yml"

echo "Deploying to $ENVIRONMENT..."

# Pull latest images
docker-compose -f "$COMPOSE_FILE" pull

# Run database migrations
docker-compose -f "$COMPOSE_FILE" run --rm api flask db upgrade

# Restart services with zero-downtime
docker-compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Wait for health check
echo "Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:5000/api/health > /dev/null 2>&1; then
        echo "Health check passed!"
        exit 0
    fi
    sleep 1
done

echo "ERROR: Health check failed after 30 seconds"
exit 1
'''

STYLES_CSS = ''':root {
  --color-primary: #3b82f6;
  --color-primary-dark: #2563eb;
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-text: #e2e8f0;
  --color-text-muted: #94a3b8;
  --color-border: #334155;
  --color-danger: #ef4444;
  --color-success: #22c55e;
  --radius: 8px;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: "Inter", -apple-system, sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.6;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  padding: 1rem 2rem;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

main {
  flex: 1;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--color-text-muted);
}

button {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.2s;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-dark);
}

.btn-danger {
  background: var(--color-danger);
  color: white;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
  border-radius: var(--radius);
  overflow: hidden;
}

.user-table th,
.user-table td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.user-table th {
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
'''

SQL_MIGRATION = '''-- Migration 001: Initial schema
-- Created: 2026-02-20

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(256),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active) WHERE is_active = TRUE;

-- Seed data for development
INSERT INTO users (name, email, password_hash, is_active)
VALUES
    ('Alice Johnson', 'alice@example.com', 'pbkdf2:sha256:placeholder', TRUE),
    ('Bob Smith', 'bob@example.com', 'pbkdf2:sha256:placeholder', TRUE),
    ('Charlie Brown', 'charlie@example.com', 'pbkdf2:sha256:placeholder', FALSE)
ON CONFLICT (email) DO NOTHING;

COMMIT;
'''

AUTH_PY = '''from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

from config import Config


def generate_token(user_id: int) -> str:
    """Generate a JWT token for the given user."""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(f):
    """Decorator that requires a valid JWT in the Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        request.user_id = payload["user_id"]
        return f(*args, **kwargs)
    return decorated
'''

REQUIREMENTS_TXT = '''flask==3.0.2
flask-cors==4.0.0
flask-sqlalchemy==3.1.1
psycopg2-binary==2.9.9
pyjwt==2.8.0
redis==5.0.1
werkzeug==3.0.1
gunicorn==21.1.0
'''

PACKAGE_JSON = '''{
  "name": "webapp-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.55",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.0"
  }
}
'''

TSCONFIG_JSON = '''{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
'''

GITIGNORE = '''# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/

# Node
node_modules/
dist/

# Environment
.env
.env.local

# IDE
.vscode/
.idea/

# Docker
pgdata/

# OS
.DS_Store
'''


# --------------------------------------------------------------------------- #
# Session builders
# --------------------------------------------------------------------------- #

def build_session_1() -> tuple[str, str, list[dict]]:
    """Session 1: Initial project setup — backend + config files.

    Project: demo-webapp (slug: -Users-demo-webapp)
    Creates: app.py, models.py, utils.py, config.py, docker-compose.yml,
             .env.example, README.md, deploy.sh, migrations/001_init.sql
    """
    sid = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    slug = "-Users-demo-webapp"
    lines: list[dict] = []

    # --- 10:00 — Create app.py ---
    lines.append(progress_line("2026-02-20T10:00:00.000Z", sid))
    write_create(lines, "2026-02-20T10:00:05.000Z", sid, f"{BASE}/app.py", APP_PY_V1)

    lines.append(progress_line("2026-02-20T10:01:00.000Z", sid))

    # --- 10:02 — Create models.py ---
    write_create(lines, "2026-02-20T10:02:00.000Z", sid, f"{BASE}/models.py", MODELS_PY_V1)

    # --- 10:05 — Create config.py ---
    lines.append(progress_line("2026-02-20T10:04:30.000Z", sid))
    write_create(lines, "2026-02-20T10:05:00.000Z", sid, f"{BASE}/config.py", CONFIG_PY)

    # --- 10:08 — Create utils.py ---
    write_create(lines, "2026-02-20T10:08:00.000Z", sid, f"{BASE}/utils.py", UTILS_PY)

    lines.append(progress_line("2026-02-20T10:09:00.000Z", sid))

    # --- 10:10 — Create docker-compose.yml ---
    write_create(lines, "2026-02-20T10:10:00.000Z", sid, f"{BASE}/docker-compose.yml", DOCKER_COMPOSE_V1)

    # --- 10:15 — Create .env.example ---
    write_create(lines, "2026-02-20T10:15:00.000Z", sid, f"{BASE}/.env.example", ENV_EXAMPLE)

    # --- 10:20 — Create README.md ---
    lines.append(progress_line("2026-02-20T10:19:00.000Z", sid))
    write_create(lines, "2026-02-20T10:20:00.000Z", sid, f"{BASE}/README.md", README_MD)

    # --- 10:25 — Create deploy.sh ---
    write_create(lines, "2026-02-20T10:25:00.000Z", sid, f"{BASE}/deploy.sh", DEPLOY_SH)

    # --- 10:30 — Create migrations/001_init.sql ---
    write_create(lines, "2026-02-20T10:30:00.000Z", sid, f"{BASE}/migrations/001_init.sql", SQL_MIGRATION)

    # --- 10:35 — Edit app.py: add version to health endpoint ---
    edit(
        lines, "2026-02-20T10:35:00.000Z", sid,
        f"{BASE}/app.py",
        'return jsonify({"status": "ok"})',
        'return jsonify({"status": "ok", "version": "0.1.0"})',
        APP_PY_V1,
    )

    lines.append(progress_line("2026-02-20T10:36:00.000Z", sid))

    # --- 10:40 — Edit models.py: add is_active field ---
    edit(
        lines, "2026-02-20T10:40:00.000Z", sid,
        f"{BASE}/models.py",
        '    created_at = db.Column(db.DateTime, server_default=db.func.now())',
        '    is_active = db.Column(db.Boolean, default=True)\n    created_at = db.Column(db.DateTime, server_default=db.func.now())',
        MODELS_PY_V1,
    )

    return slug, sid, lines


def build_session_2() -> tuple[str, str, list[dict]]:
    """Session 2: Frontend + auth — a few hours later.

    Project: demo-webapp (slug: -Users-demo-webapp)
    Creates: App.tsx, api.ts, hooks/useAuth.ts, styles.css, nginx.conf,
             ARCHITECTURE.md, auth.py
    Edits: app.py (rewrite v2), models.py (rewrite v2), docker-compose.yml (edit)
    Reads: config.py, utils.py
    """
    sid = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
    slug = "-Users-demo-webapp"
    lines: list[dict] = []

    # --- 14:00 — Read config.py to understand setup ---
    lines.append(progress_line("2026-02-20T14:00:00.000Z", sid))
    read(lines, "2026-02-20T14:00:05.000Z", sid, f"{BASE}/config.py", CONFIG_PY)

    # --- 14:02 — Read utils.py ---
    read(lines, "2026-02-20T14:02:00.000Z", sid, f"{BASE}/utils.py", UTILS_PY)

    lines.append(progress_line("2026-02-20T14:03:00.000Z", sid))

    # --- 14:05 — Create auth.py ---
    write_create(lines, "2026-02-20T14:05:00.000Z", sid, f"{BASE}/auth.py", AUTH_PY)

    # --- 14:10 — Rewrite app.py with auth + create_user route ---
    write_update(lines, "2026-02-20T14:10:00.000Z", sid, f"{BASE}/app.py", APP_PY_V2, APP_PY_V1)

    # --- 14:15 — Rewrite models.py with password support ---
    write_update(lines, "2026-02-20T14:15:00.000Z", sid, f"{BASE}/models.py", MODELS_PY_V2, MODELS_PY_V1)

    lines.append(progress_line("2026-02-20T14:16:00.000Z", sid))

    # --- 14:20 — Create App.tsx ---
    write_create(lines, "2026-02-20T14:20:00.000Z", sid, f"{BASE}/frontend/src/App.tsx", APP_TSX_V1)

    # --- 14:25 — Create api.ts ---
    write_create(lines, "2026-02-20T14:25:00.000Z", sid, f"{BASE}/frontend/src/api.ts", API_TS)

    # --- 14:30 — Create useAuth.ts ---
    write_create(lines, "2026-02-20T14:30:00.000Z", sid, f"{BASE}/frontend/src/hooks/useAuth.ts", USE_AUTH_TS)

    # --- 14:35 — Create styles.css ---
    write_create(lines, "2026-02-20T14:35:00.000Z", sid, f"{BASE}/frontend/src/styles.css", STYLES_CSS)

    lines.append(progress_line("2026-02-20T14:36:00.000Z", sid))

    # --- 14:40 — Create nginx.conf ---
    write_create(lines, "2026-02-20T14:40:00.000Z", sid, f"{BASE}/nginx.conf", NGINX_CONF)

    # --- 14:45 — Create ARCHITECTURE.md ---
    write_create(lines, "2026-02-20T14:45:00.000Z", sid, f"{BASE}/ARCHITECTURE.md", ARCHITECTURE_MD)

    # --- 14:50 — Edit docker-compose: add redis + healthcheck ---
    write_update(
        lines, "2026-02-20T14:50:00.000Z", sid,
        f"{BASE}/docker-compose.yml", DOCKER_COMPOSE_V2, DOCKER_COMPOSE_V1,
    )

    # --- 14:55 — Edit App.tsx: add routing + protected routes ---
    write_update(
        lines, "2026-02-20T14:55:00.000Z", sid,
        f"{BASE}/frontend/src/App.tsx", APP_TSX_V2, APP_TSX_V1,
    )

    return slug, sid, lines


def build_session_3() -> tuple[str, str, list[dict]]:
    """Session 3: Config files for a second project (frontend tooling).

    Project: demo-webapp-frontend (slug: -Users-demo-webapp-frontend)
    Creates: package.json, tsconfig.json, .gitignore
    Creates: requirements.txt (in backend dir)
    Reads: App.tsx
    """
    sid = "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f"
    slug = "-Users-demo-webapp-frontend"
    lines: list[dict] = []

    # --- 16:00 — Create package.json ---
    lines.append(progress_line("2026-02-20T16:00:00.000Z", sid))
    write_create(lines, "2026-02-20T16:00:05.000Z", sid, f"{BASE}/frontend/package.json", PACKAGE_JSON)

    # --- 16:05 — Create tsconfig.json ---
    write_create(lines, "2026-02-20T16:05:00.000Z", sid, f"{BASE}/frontend/tsconfig.json", TSCONFIG_JSON)

    # --- 16:10 — Create .gitignore ---
    write_create(lines, "2026-02-20T16:10:00.000Z", sid, f"{BASE}/.gitignore", GITIGNORE)

    lines.append(progress_line("2026-02-20T16:11:00.000Z", sid))

    # --- 16:15 — Create requirements.txt ---
    write_create(lines, "2026-02-20T16:15:00.000Z", sid, f"{BASE}/backend/requirements.txt", REQUIREMENTS_TXT)

    # --- 16:20 — Read App.tsx to review ---
    read(lines, "2026-02-20T16:20:00.000Z", sid, f"{BASE}/frontend/src/App.tsx", APP_TSX_V2)

    # --- 16:25 — Edit .gitignore: add more patterns ---
    current_gitignore = GITIGNORE
    edit(
        lines, "2026-02-20T16:25:00.000Z", sid,
        f"{BASE}/.gitignore",
        "# OS\n.DS_Store",
        "# OS\n.DS_Store\nThumbs.db\n\n# Logs\n*.log\nnpm-debug.log*",
        current_gitignore,
    )

    return slug, sid, lines


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def write_session(slug: str, session_id: str, entries: list[dict]) -> None:
    """Write a list of JSONL entries to the appropriate file."""
    session_dir = DEMO_DIR / slug
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"{session_id}.jsonl"

    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"  Wrote {len(entries)} lines to {path.relative_to(DEMO_DIR.parent.parent)}")


def main():
    # Clean existing demo data
    import shutil
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)

    print("Generating demo data...")
    print()

    slug1, sid1, entries1 = build_session_1()
    write_session(slug1, sid1, entries1)

    slug2, sid2, entries2 = build_session_2()
    write_session(slug2, sid2, entries2)

    slug3, sid3, entries3 = build_session_3()
    write_session(slug3, sid3, entries3)

    print()
    print("Done! Demo data written to demo/demo-claude-data/")
    print()

    # Quick summary
    all_files = set()
    for entries in [entries1, entries2, entries3]:
        for e in entries:
            if e.get("type") == "assistant":
                for block in e.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        fp = block.get("input", {}).get("file_path", "")
                        if fp:
                            all_files.add(fp)
    print(f"Files touched across all sessions: {len(all_files)}")
    for fp in sorted(all_files):
        print(f"  {fp}")


if __name__ == "__main__":
    main()
