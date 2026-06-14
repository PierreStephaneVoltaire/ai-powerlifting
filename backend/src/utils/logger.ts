import pino from 'pino'

const logLevel = process.env.LOG_LEVEL || 'info'

export const logger = pino({
  level: logLevel,
  formatters: {
    level(label) {
      return { level: label }
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
})

export default logger
