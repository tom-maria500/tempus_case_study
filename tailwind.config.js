/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Tempus-inspired shell
        'bg-primary': '#050816',
        'bg-secondary': '#0B1020',
        'bg-tertiary': '#12172A',
        'bg-border': '#1E2D40',
        'text-primary': '#F5F7FF',
        'text-secondary': '#9CA9C8',
        'text-muted': '#4A5568',
        // Tempus teal accent
        'accent-primary': '#00C2B2',
        'accent-hover': '#00A89A',
        'accent-subtle': '#0D2E2C',
        // Semantic
        success: '#10B981',
        warning: '#F59E0B',
        danger: '#EF4444',
        info: '#3B82F6',
        // Priority scores
        'priority-high': '#00C2B2',
        'priority-mid': '#F59E0B',
        'priority-low': '#4A5568'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace']
      },
      boxShadow: {
        tempus: '0 1px 3px rgba(15,23,42,0.6), 0 18px 45px rgba(15,23,42,0.85)'
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #00C2B2, #0099A8)'
      },
      borderRadius: {
        card: '8px',
        input: '6px',
        badge: '4px'
      },
      transitionDuration: {
        150: '150ms',
        200: '200ms',
        400: '400ms'
      }
    }
  },
  plugins: []
};

