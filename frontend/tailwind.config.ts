import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Core void palette - deep layered blacks
        void: 'rgb(var(--color-void) / <alpha-value>)',
        abyss: 'rgb(var(--color-abyss) / <alpha-value>)',
        surface: 'rgb(var(--color-surface) / <alpha-value>)',
        elevated: 'rgb(var(--color-elevated) / <alpha-value>)',

        // Velocity accent palette
        boost: {
          DEFAULT: 'rgb(var(--color-boost) / <alpha-value>)',
          50: '#e6faff',
          100: '#b3f0ff',
          200: '#80e6ff',
          300: '#4ddcff',
          400: '#1ad2ff',
          500: '#00d4ff', // Primary
          600: '#00b8e6',
          700: '#008fb3',
          800: '#006680',
          900: '#003d4d',
        },
        fire: {
          DEFAULT: 'rgb(var(--color-fire) / <alpha-value>)',
          50: '#fff5f0',
          100: '#ffe0d1',
          200: '#ffcbb3',
          300: '#ffb694',
          400: '#ffa176',
          500: '#ff6b35', // Primary
          600: '#e65a2a',
          700: '#cc4a1f',
          800: '#993815',
          900: '#66260e',
        },
        plasma: {
          DEFAULT: 'rgb(var(--color-plasma) / <alpha-value>)',
          500: '#8b5cf6',
        },
        victory: {
          DEFAULT: 'rgb(var(--color-victory) / <alpha-value>)',
          500: '#10b981',
        },
        defeat: {
          DEFAULT: 'rgb(var(--color-defeat) / <alpha-value>)',
          500: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
        display: ['Bebas Neue', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        // Custom fluid scale for stats
        'stat-xl': ['4rem', { lineHeight: '1', letterSpacing: '0.02em' }],
        'stat-lg': ['3rem', { lineHeight: '1', letterSpacing: '0.02em' }],
        'stat-md': ['2rem', { lineHeight: '1', letterSpacing: '0.02em' }],
        'stat-sm': ['1.5rem', { lineHeight: '1', letterSpacing: '0.02em' }],
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        'glow-sm': '0 0 10px rgba(0, 212, 255, 0.3)',
        'glow-md': '0 0 20px rgba(0, 212, 255, 0.3)',
        'glow-lg': '0 0 40px rgba(0, 212, 255, 0.3)',
        'glow-fire': '0 0 20px rgba(255, 107, 53, 0.3)',
        'glow-fire-lg': '0 0 40px rgba(255, 107, 53, 0.3)',
        'inner-glow': 'inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        'card': '0 4px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.03)',
        'card-hover': '0 8px 40px rgba(0, 0, 0, 0.5), 0 0 30px rgba(0, 212, 255, 0.1)',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-boost': 'linear-gradient(135deg, rgb(var(--color-boost)), rgb(var(--color-fire)))',
        'gradient-fire': 'linear-gradient(135deg, rgb(var(--color-fire)), #ff8f5a)',
        'gradient-surface': 'linear-gradient(135deg, rgb(18 22 32 / 0.9), rgb(12 14 20 / 0.8))',
        'grid-pattern': `linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
                         linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)`,
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
      animation: {
        'fade-in': 'fade-in 0.4s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'slide-in-right': 'slide-in-right 0.3s ease-out',
        'scale-in': 'scale-in 0.3s ease-out',
        'float': 'float 3s ease-in-out infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-ring': 'pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'gradient-shift': 'gradient-shift 3s ease infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          from: { opacity: '0', transform: 'translateX(20px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
        'pulse-ring': {
          '0%, 100%': { opacity: '0.5', transform: 'scale(1)' },
          '50%': { opacity: '0', transform: 'scale(1.1)' },
        },
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.3)' },
          '50%': { boxShadow: '0 0 40px rgba(0, 212, 255, 0.5)' },
        },
        'gradient-shift': {
          '0%, 100%': { backgroundPosition: '0% center' },
          '50%': { backgroundPosition: '200% center' },
        },
      },
      transitionTimingFunction: {
        'bounce-in': 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};

export default config;
