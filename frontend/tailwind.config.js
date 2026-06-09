/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './app.js'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      colors: {
        slate: { 850: '#172033', 950: '#0b1220' },
      },
    },
  },
  plugins: [],
};
