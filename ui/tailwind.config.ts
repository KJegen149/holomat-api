import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        j: {
          bg:        'rgb(5 6 9 / <alpha-value>)',
          surf:      'rgb(15 20 28 / <alpha-value>)',
          'surf-hi': 'rgb(25 32 42 / <alpha-value>)',
          'surf-lo': 'rgb(10 14 20 / <alpha-value>)',
          border:    'rgb(0 200 232 / <alpha-value>)',
          'border-vi': 'rgb(140 110 255 / <alpha-value>)',
          cyan:      'rgb(0 220 255 / <alpha-value>)',
          cdim:      'rgb(0 130 160 / <alpha-value>)',
          cdeep:     'rgb(0 80 110 / <alpha-value>)',
          violet:    'rgb(140 110 255 / <alpha-value>)',
          vdim:      'rgb(80 60 160 / <alpha-value>)',
          text:      'rgb(220 240 248 / <alpha-value>)',
          muted:     'rgb(120 160 175 / <alpha-value>)',
          'muted-dim': 'rgb(70 100 115 / <alpha-value>)',
          green:     'rgb(50 255 160 / <alpha-value>)',
          amber:     'rgb(255 180 60 / <alpha-value>)',
          red:       'rgb(255 80 100 / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Rajdhani', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        'j-sm':   '10px',
        'j-md':   '16px',
        'j-lg':   '22px',
        'j-xl':   '32px',
      },
      backdropBlur: {
        'j': '16px',
      },
      backgroundImage: {
        'j-brand': 'linear-gradient(120deg, rgb(0 220 255), rgb(140 110 255) 120%)',
        'j-ambient': `
          radial-gradient(ellipse at 25% 15%, rgba(80, 60, 160, 0.14) 0%, transparent 55%),
          radial-gradient(ellipse at 75% 85%, rgba(0, 130, 160, 0.12) 0%, transparent 55%),
          radial-gradient(ellipse at 50% 50%, rgba(20, 30, 50, 0.5) 0%, transparent 70%)
        `,
      },
      boxShadow: {
        'j-panel': 'inset 0 1px 0 rgba(255, 255, 255, 0.04), inset 0 0 24px rgba(0, 220, 255, 0.04), 0 12px 40px rgba(0, 0, 0, 0.45)',
        'j-glow':  '0 0 26px rgba(0, 220, 255, 0.35)',
        'j-glow-violet': '0 0 26px rgba(140, 110, 255, 0.35)',
      },
      animation: {
        'spin-slow':     'spin 20s linear infinite',
        'spin-rslw':     'spin 14s linear infinite reverse',
        'spin-med':      'spin 8s linear infinite',
        'spin-rmed':     'spin 4s linear infinite reverse',
        'radar-sweep':   'spin 4s linear infinite',
        'pulse-green':   'pulse-green 2s ease-in-out infinite',
        'cur-blink':     'cur-blink 1s step-end infinite',
        'tick-blink':    'tick-blink 4s ease-in-out infinite',
        'j-breathe':     'j-breathe 2.4s ease-in-out infinite',
        'j-orb-pulse':   'j-orb-pulse 2.6s ease-in-out infinite',
      },
      keyframes: {
        'pulse-green': {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0.4' },
        },
        'cur-blink': {
          '0%, 100%': { opacity: '1' },
          '50%':       { opacity: '0' },
        },
        'tick-blink': {
          '0%, 45%, 100%': { opacity: '0' },
          '50%, 55%':      { opacity: '1' },
        },
        'j-breathe': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%':       { opacity: '0.45', transform: 'scale(0.85)' },
        },
        'j-orb-pulse': {
          '0%, 100%': { transform: 'scale(1)',    boxShadow: '0 0 24px rgba(0,220,255,0.35), inset 0 0 12px rgba(0,220,255,0.2)' },
          '50%':       { transform: 'scale(1.08)', boxShadow: '0 0 36px rgba(0,220,255,0.6),  inset 0 0 16px rgba(0,220,255,0.35)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
