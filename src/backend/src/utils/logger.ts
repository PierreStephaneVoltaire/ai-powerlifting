import pino from 'pino'

const logLevel = process.env.LOG_LEVEL || 'info'

export const logger = pino({
  level: logLevel,
  redact: {
    paths: ['req.headers.authorization', 'req.headers.cookie', 'res.headers["set-cookie"]'],
    remove: true,
  },
  formatters: {
    level(label) {
      return { level: label }
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
})

