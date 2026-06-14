export default {
  plugins: {
    'postcss-preset-mantine': {},
    'postcss-simple-vars': {
      variables: {
        'mantine-breakpoint-xs': '36em',
      },
    },
    tailwindcss: {},
    autoprefixer: {},
  },
}
