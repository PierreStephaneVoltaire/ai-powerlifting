# Proposals Portal

Full-stack web application for reviewing, approving, and submitting system improvement proposals.

Frontend is built on the same Mantine v9 + CSS token design system used by the powerlifting app, directives portal, and main portal.

## Quick Start

```bash
# Install dependencies (root + all workspaces)
npm install

# Copy environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Edit backend/.env with your AWS credentials and OpenRouter API key

# Build shared types
npm run build -w packages/types

# Start development servers
npm run dev
```

## Services

- **Backend**: http://localhost:3004
- **Frontend**: http://localhost:5173

## API Endpoints

### Proposals
- `GET /api/proposals` - List all proposals
- `GET /api/proposals/:sk` - Get single proposal
- `POST /api/proposals` - Create proposal
- `PATCH /api/proposals/:sk/approve` - Approve proposal (synchronously generates the implementation plan; the plan is returned in the response)
- `PATCH /api/proposals/:sk/reject` - Reject proposal
- `DELETE /api/proposals/:sk` - Delete pending proposal
- `POST /api/proposals/:sk/generate-plan` - Regenerate the implementation plan for an approved proposal
- `GET /api/proposals/:sk/plan` - Get implementation plan

### Directives
- `GET /api/directives` - List all active directives
- `GET /api/directives/:sk` - Get specific directive

## Tech Stack

- **Frontend**: React 19 + Vite 5 + TypeScript + Mantine v9 + Tailwind CSS (utility-residual)
- **Backend**: Node.js 20 + Express 5 + TypeScript
- **Database**: DynamoDB (table: `if-proposals`)
- **State Management**: Zustand

Plan generation is part of the approve response — no WebSocket subscription is needed on the client.
