import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { errorHandler } from './middleware/errorHandler';
import proposalsRouter from './routes/proposals';
import directivesRouter from './routes/directives';

const app = express();
const PORT = process.env.PORT || 3004;

// Middleware
app.use(cors());
app.use(express.json());

// Request logging
app.use((req, _res, next) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

// Routes
app.get('/health', (_req, res) => {
  res.json({
    status: 'healthy',
    service: 'proposals-portal-backend',
    timestamp: new Date().toISOString(),
  });
});

app.use('/api/proposals', proposalsRouter);
app.use('/api/directives', directivesRouter);

// 404 handler
app.use((_req, res) => {
  res.status(404).json({
    status: 'error',
    message: 'Not found',
  });
});

// Error handler
app.use(errorHandler);

// Start server
app.listen(PORT, () => {
  console.log(`Proposals Portal Backend running on port ${PORT}`);
});

export { app };
