import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

// Keyboard shortcuts hook
export function useKeyboardShortcuts({
  onHighlight,
  onAddNote,
  onDelete,
  onNext,
  onPrev,
  onSave,
  onFocusSearch,
  onBack,
  isDetailPage = false,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignore if user is typing in an input/textarea
      const tag = e.target.tagName.toLowerCase();
      const isInput = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

      // Global: A - Go to add link
      if (e.key.toLowerCase() === 'a' && !isInput && location.pathname !== '/add-link') {
        e.preventDefault();
        navigate('/add-link');
        return;
      }

      // Detail page shortcuts
      if (isDetailPage) {
        // Z - Back to highlights
        if (e.key.toLowerCase() === 'z' && !isInput) {
          e.preventDefault();
          navigate('/highlights');
          return;
        }

        // M - Add note / Focus note input
        if ((e.key.toLowerCase() === 'm' || e.key === 'Enter') && !isInput) {
          e.preventDefault();
          const input = document.getElementById('note-input');
          if (input) {
            input.scrollIntoView({ behavior: 'smooth', block: 'center' });
            input.focus();
          }
          return;
        }

        // H - Quick highlight (if text is selected)
        if (e.key.toLowerCase() === 'h' && !isInput) {
          const selection = window.getSelection();
          const text = selection ? selection.toString().trim() : '';
          if (text && onHighlight) {
            e.preventDefault();
            onHighlight(text);
          }
          return;
        }

        // J - Next annotation
        if (e.key.toLowerCase() === 'j' && !isInput) {
          e.preventDefault();
          if (onNext) onNext();
          return;
        }

        // K - Previous annotation
        if (e.key.toLowerCase() === 'k' && !isInput) {
          e.preventDefault();
          if (onPrev) onPrev();
          return;
        }

        // Delete/Backspace - Delete selected annotation
        if ((e.key === 'Delete' || e.key === 'Backspace') && !isInput) {
          e.preventDefault();
          if (onDelete) onDelete();
          return;
        }

        // Cmd/Ctrl + S - Save note
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
          e.preventDefault();
          if (onSave) onSave();
          return;
        }

        // Cmd/Ctrl + F - Focus search
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f') {
          e.preventDefault();
          if (onFocusSearch) {
            onFocusSearch();
          } else {
            const searchInput = document.querySelector('input[type="text"], input[placeholder*="搜索"]');
            if (searchInput) {
              searchInput.focus();
            }
          }
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate, location, isDetailPage, onHighlight, onAddNote, onDelete, onNext, onPrev, onSave, onFocusSearch, onBack]);
}

export default useKeyboardShortcuts;
