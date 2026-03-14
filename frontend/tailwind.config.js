/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        foreground: '#fafafa',
        primary: {
          DEFAULT: '#3b82f6',
          foreground: '#ffffff',
        },
        muted: '#27272a',
        'muted-foreground': '#a1a1aa',
        card: '#18181b',
        'card-foreground': '#fafafa',
        border: '#27272a',
      },
      spacing: {
        '0': '0px',
        '1': '4px',
        '2': '8px',
        '3': '12px',
        '4': '16px',
        '5': '20px',
        '6': '24px',
        '8': '32px',
        '10': '40px',
        '12': '48px',
        '16': '64px',
      }
    },
  },
  plugins: [],
}
