import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

// Global keyboard shortcuts hook (works on any page)
export function useGlobalKeyboardShortcuts() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignore if user is typing in an input/textarea
      const tag = e.target.tagName.toLowerCase();
      const isInput = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

      // Ignore if Ctrl/Cmd is pressed (browser shortcuts)
      if (e.metaKey || e.ctrlKey) return;

      // Ignore if Alt is pressed
      if (e.altKey) return;

      // A - Go to add link page
      if (e.key.toLowerCase() === 'a' && !isInput && location.pathname !== '/add-link') {
        e.preventDefault();
        navigate('/add-link');
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate, location]);
}

export default useGlobalKeyboardShortcuts;
