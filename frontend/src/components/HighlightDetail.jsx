import { useState, useEffect, useRef, memo } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, Star, Check, Trash2, Plus, Lightbulb, ExternalLink, Sparkles, Highlighter, Download, Copy } from 'lucide-react';
import api from '../api';
import { exportHighlightAsMarkdown } from '../exportMarkdown';

// Custom components to Render highlights in markdown
// memo prevents re-render when parent state changes (selectedText/menuPos),
// which would replace DOM text nodes and destroy the active browser selection.
const HighlightedMarkdown = memo(function HighlightedMarkdown({ content, annotations }) {
  const annotationsWithText = annotations?.filter(a => a.selected_text && a.selected_text.trim()) || [];

  // Reusable ReactMarkdown with custom img
  const renderMarkdown = (text) => (
    <ReactMarkdown
      components={{
        img: ({ node, src, alt, ...props }) => (
          <img
            src={src}
            alt={alt}
            referrerPolicy="no-referrer"
            {...props}
          />
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );

  if (annotationsWithText.length === 0) {
    return renderMarkdown(content);
  }

  const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = annotationsWithText
    .map(a => a.selected_text.trim())
    .sort((a, b) => b.length - a.length);

  if (patterns.length === 0) {
    return renderMarkdown(content);
  }

  const pattern = new RegExp(`(${patterns.map(escapeRegex).join('|')})`, 'gi');

  return (
    <ReactMarkdown
      components={{
        img: ({ node, src, alt, ...props }) => (
          <img
            src={src}
            alt={alt}
            referrerPolicy="no-referrer"
            {...props}
          />
        ),
        p: ({ node, children, ...props }) => {
          const textContent = extractText(children);
          if (!textContent) return <p {...props}>{children}</p>;

          const childParts = String(textContent).split(pattern);
          if (childParts.length === 1) return <p {...props}>{children}</p>;

          const newChildren = [];
          childParts.forEach((part, i) => {
            if (i > 0) newChildren.push(' ');
            const isMatch = patterns.some(p => part.toLowerCase() === p.toLowerCase());
            if (isMatch) {
              newChildren.push(
                <mark key={i} className="bg-yellow-200 px-0.5 rounded">
                  {part}
                </mark>
              );
            } else {
              newChildren.push(part);
            }
          });

          return <p {...props}>{newChildren}</p>;
        },
        text: ({ node, children, ...props }) => {
          const textContent = children;
          if (typeof textContent !== 'string') return <span {...props}>{children}</span>;

          const childParts = textContent.split(pattern);
          if (childParts.length === 1) return <span {...props}>{children}</span>;

          return (
            <>
              {childParts.map((part, i) => {
                const isMatch = patterns.some(p => part.toLowerCase() === p.toLowerCase());
                if (isMatch) {
                  return <mark key={i} className="bg-yellow-200 px-0.5 rounded">{part}</mark>;
                }
                return part;
              })}
            </>
          );
        }
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

function extractText(children) {
  if (!children) return '';
  if (typeof children === 'string') return children;
  if (Array.isArray(children)) return children.map(extractText).join('');
  if (children.props?.children) return extractText(children.props.children);
  return '';
}

export default function HighlightDetail() {
  const { id } = useParams();
  const contentRef = useRef(null);
  const noteInputRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newNote, setNewNote] = useState('');
  const [suggestedTags, setSuggestedTags] = useState([]);
  const [summary, setSummary] = useState('');
  const [menuPos, setMenuPos] = useState(null);
  const [selectedText, setSelectedText] = useState('');
  const [selectedAnnotationIndex, setSelectedAnnotationIndex] = useState(-1);
  const [editingAnnotationId, setEditingAnnotationId] = useState(null);
  const [editingNote, setEditingNote] = useState('');
  const scrollPositionRef = useRef(0);
  const annotationRefs = useRef([]);
  const menuRef = useRef(null);

  const loadHighlight = async (saveScroll = false) => {
    if (saveScroll) {
      scrollPositionRef.current = window.scrollY;
    }

    setLoading(true);
    try {
      const result = await api.highlight(id);
      setData(result);
      setSummary(result.highlight.summary || '');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (saveScroll) {
        setTimeout(() => {
          window.scrollTo(0, scrollPositionRef.current);
        }, 0);
      }
    }
  };

  useEffect(() => {
    loadHighlight();
  }, [id]);

  const handleToggleFavorite = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.toggleFavorite(id).then(updated => {
      setData(prev => ({ ...prev, highlight: updated }));
    });
  };

  const handleToggleRead = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.toggleRead(id).then(updated => {
      setData(prev => ({ ...prev, highlight: updated }));
    });
  };

  const handleDelete = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!confirm('确定要删除这条摘录吗？')) return;
    api.deleteHighlight(id).then(() => {
      window.location.href = '/highlights';
    });
  };

  const handleAddHighlightOnly = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!selectedText.trim()) return;

    const currentScroll = window.scrollY;

    api.createAnnotation({
      highlight_id: parseInt(id),
      selected_text: selectedText,
      note: '',
    }).then(() => {
      setSelectedText('');
      setMenuPos(null);
      return api.highlight(id);
    }).then(result => {
      setData(result);
      setSummary(result.highlight.summary || '');
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    });
  };

  const handleAddNote = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!newNote.trim()) {
      setMenuPos(null);
      return;
    }

    const currentScroll = window.scrollY;

    api.createAnnotation({
      highlight_id: parseInt(id),
      selected_text: selectedText,
      note: newNote,
    }).then(() => {
      setNewNote('');
      setSelectedText('');
      setMenuPos(null);
      return api.highlight(id);
    }).then(result => {
      setData(result);
      setSummary(result.highlight.summary || '');
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    });
  };

  const handleEditAnnotation = (annotation, e) => {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    setEditingAnnotationId(annotation.id);
    setEditingNote(annotation.note || '');
  };

  const handleSaveAnnotationNote = (annotationId, e) => {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    const currentScroll = window.scrollY;
    api.updateAnnotation(annotationId, { note: editingNote }).then(() => {
      setEditingAnnotationId(null);
      setEditingNote('');
      return api.highlight(id);
    }).then(result => {
      setData(result);
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    }).catch(err => {
      console.error('保存评价失败:', err);
      alert('保存失败：' + err.message);
    });
  };

  const handleDeleteAnnotation = (annotationId, e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const currentScroll = window.scrollY;
    api.deleteAnnotation(annotationId).then(() => {
      return api.highlight(id);
    }).then(result => {
      setData(result);
      setSummary(result.highlight.summary || '');
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    });
  };

  const handleSuggestTags = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.suggestTags(data.highlight.text, data.highlight.tags || '').then(result => {
      setSuggestedTags(result.tags);
    }).catch(console.error);
  };

  const handleSummarize = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const currentScroll = window.scrollY;
    api.summarize(data.highlight.text).then(result => {
      setSummary(result.summary);
      // 不保存错误信息到数据库
      if (result.summary && !result.summary.startsWith('[API错误]') && !result.summary.startsWith('[错误]')) {
        return api.updateHighlight(id, { summary: result.summary });
      }
    }).then(() => {
      return api.highlight(id);
    }).then(result => {
      setData(prev => ({ ...prev, highlight: { ...prev.highlight, summary: result.highlight.summary } }));
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    }).catch(console.error);
  };

  const handleAddTag = (tagName, e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const currentTags = data.highlight.tags || '';
    const newTags = currentTags ? `${currentTags},${tagName}` : tagName;
    api.updateHighlight(id, { tags: newTags }).then(() => {
      return api.highlight(id);
    }).then(result => {
      setData(result);
      setSuggestedTags(prev => prev.filter(t => t !== tagName));
    });
  };

  // Show menu after selection gesture ends (mouseup/touchend — not during drag)
  useEffect(() => {
    const showMenuIfSelected = () => {
      setTimeout(() => {
        const selection = window.getSelection();
        const text = selection?.toString().trim() || '';
        if (text && selection.rangeCount > 0) {
          const range = selection.getRangeAt(0);
          if (contentRef.current && contentRef.current.contains(range.startContainer)) {
            setSelectedText(text);
            const rect = range.getBoundingClientRect();
            const menuWidth = 252;
            const menuHeight = 44;
            const gap = 8;
            let x = rect.left + rect.width / 2 - menuWidth / 2;
            let y = rect.bottom + gap;
            x = Math.max(8, Math.min(x, window.innerWidth - menuWidth - 8));
            if (y + menuHeight > window.innerHeight - 8) {
              y = rect.top - menuHeight - gap;
            }
            setMenuPos({ x, y });
            return;
          }
        }
        setMenuPos(null);
        setSelectedText('');
      }, 30);
    };

    document.addEventListener('mouseup', showMenuIfSelected);
    document.addEventListener('touchend', showMenuIfSelected);
    return () => {
      document.removeEventListener('mouseup', showMenuIfSelected);
      document.removeEventListener('touchend', showMenuIfSelected);
    };
  }, []);

  // Close menu on outside press — only mounted while menu is visible,
  // so there are zero state updates during the selection gesture itself.
  useEffect(() => {
    if (!menuPos) return;
    const handleOutsidePress = (e) => {
      if (menuRef.current && menuRef.current.contains(e.target)) return;
      setMenuPos(null);
      setSelectedText('');
    };
    // Small delay so the touchend that just opened the menu doesn't immediately close it
    const t = setTimeout(() => {
      document.addEventListener('touchstart', handleOutsidePress, { once: false });
      document.addEventListener('mousedown', handleOutsidePress, { once: false });
    }, 50);
    return () => {
      clearTimeout(t);
      document.removeEventListener('touchstart', handleOutsidePress);
      document.removeEventListener('mousedown', handleOutsidePress);
    };
  }, [menuPos]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignore if typing in input
      const tag = e.target.tagName.toLowerCase();
      const isInput = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

      // Z - Back to highlights
      if (e.key.toLowerCase() === 'z' && !isInput) {
        e.preventDefault();
        window.location.href = '/highlights';
        return;
      }

      // M or Enter - Focus note input
      if ((e.key.toLowerCase() === 'm' || e.key === 'Enter') && !isInput) {
        e.preventDefault();
        const input = document.getElementById('note-input');
        if (input) {
          input.scrollIntoView({ behavior: 'smooth', block: 'center' });
          input.focus();
        }
        return;
      }

      // H - Quick highlight selected text
      if (e.key.toLowerCase() === 'h' && !isInput) {
        const selection = window.getSelection();
        const text = selection ? selection.toString().trim() : '';
        if (text) {
          // Save scroll position BEFORE preventDefault
          const currentScroll = window.scrollY;
          e.preventDefault();
          api.createAnnotation({
            highlight_id: parseInt(id),
            selected_text: text,
            note: '',
          }).then(() => {
            // Restore scroll position after load
            setTimeout(() => window.scrollTo(0, currentScroll), 10);
            loadHighlight();
          });
        }
        return;
      }

      // J - Next annotation
      if (e.key.toLowerCase() === 'j' && !isInput) {
        e.preventDefault();
        if (data?.annotations?.length > 0) {
          const nextIndex = (selectedAnnotationIndex + 1) % data.annotations.length;
          setSelectedAnnotationIndex(nextIndex);
          annotationRefs.current[nextIndex]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }

      // K - Previous annotation
      if (e.key.toLowerCase() === 'k' && !isInput) {
        e.preventDefault();
        if (data?.annotations?.length > 0) {
          const prevIndex = selectedAnnotationIndex <= 0 ? data.annotations.length - 1 : selectedAnnotationIndex - 1;
          setSelectedAnnotationIndex(prevIndex);
          annotationRefs.current[prevIndex]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }

      // Delete/Backspace - Delete selected annotation
      if ((e.key === 'Delete' || e.key === 'Backspace') && !isInput) {
        if (selectedAnnotationIndex >= 0 && data?.annotations?.[selectedAnnotationIndex]) {
          e.preventDefault();
          const annotation = data.annotations[selectedAnnotationIndex];
          if (confirm('确定要删除这条笔记吗？')) {
            handleDeleteAnnotation(annotation.id, { preventDefault: () => {}, stopPropagation: () => {} });
          }
        }
        return;
      }

      // Ctrl/Cmd + S - Save note
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (newNote.trim()) {
          handleAddNote({ preventDefault: () => {}, stopPropagation: () => {} });
        }
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [data, selectedAnnotationIndex, newNote, selectedText]);

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center py-20">
          <div className="spinner w-8 h-8"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <div className="card p-8 text-center">
          <div className="text-red-500 mb-4">加载失败: {error}</div>
          <Link to="/highlights" className="btn btn-primary" onClick={e => e.preventDefault()}>
            返回列表
          </Link>
        </div>
      </div>
    );
  }

  const { highlight, annotations } = data;
  const tags = highlight.tags ? highlight.tags.split(',').map(t => t.trim()).filter(Boolean) : [];

  return (
    <div className="page-container">
      <Link
        to="/highlights"
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 transition-colors"
        onClick={e => {
          e.preventDefault();
          window.location.href = '/highlights';
        }}
      >
        <ArrowLeft size={18} />
        返回列表
      </Link>

      <div className="flex gap-2 mb-6">
        <button
          onClick={handleToggleFavorite}
          className={`btn ${highlight.favorite ? 'bg-yellow-50 border-yellow-300 text-yellow-700' : 'btn-secondary'}`}
        >
          <Star size={16} className="inline mr-1" fill={highlight.favorite ? 'currentColor' : 'none'} />
          {highlight.favorite ? '已收藏' : '收藏'}
        </button>
        <button
          onClick={handleToggleRead}
          className={`btn ${highlight.is_read ? 'btn-secondary' : 'bg-green-50 border-green-300 text-green-700'}`}
        >
          <Check size={16} className="inline mr-1" />
          {highlight.is_read ? '标记未读' : '标记已读'}
        </button>
        <button
          onClick={() => exportHighlightAsMarkdown(highlight, annotations)}
          className="btn btn-secondary"
          title="导出 Markdown"
        >
          <Download size={16} className="inline mr-1" />
          导出
        </button>
        <button
          onClick={handleDelete}
          className="btn btn-secondary text-red-500 hover:bg-red-50 ml-auto"
        >
          <Trash2 size={16} className="inline mr-1" />
          删除
        </button>
      </div>

      <div className="card p-6 mb-6">
        <div className="flex items-center gap-3 text-sm text-gray-400 mb-5 pb-5 border-b border-gray-100">
          {highlight.source && (
            <>
              <span className="font-medium text-gray-600">{highlight.source}</span>
              {highlight.author && <span className="text-gray-400">- {highlight.author}</span>}
            </>
          )}
          {highlight.location && (
            <a
              href={highlight.location}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto text-blue-500 hover:text-blue-600 flex items-center gap-1"
            >
              查看原文 <ExternalLink size={12} />
            </a>
          )}
        </div>

        {/* Summary section - show before text */}
        {summary && (
          <div className="mb-6 p-4 bg-gradient-to-r from-amber-50 to-yellow-50 rounded-lg border border-amber-100">
            <div className="flex items-center gap-2 text-sm font-medium text-amber-700 mb-2">
              <Lightbulb size={16} />
              摘要
            </div>
            <p className="text-gray-700">{summary}</p>
          </div>
        )}

        {/* AI buttons row - show before text if no summary */}
        {!summary && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <button
              onClick={handleSummarize}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-amber-50 text-amber-600 rounded-full hover:bg-amber-100 transition-colors"
            >
              <Sparkles size={12} />
              生成摘要
            </button>
            <button
              onClick={handleSuggestTags}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-50 text-blue-600 rounded-full hover:bg-blue-100 transition-colors"
            >
              <Sparkles size={12} />
              AI 推荐标签
            </button>
          </div>
        )}

        {/* Show AI buttons after tags if summary exists */}
        {summary && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <button
              onClick={handleSuggestTags}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-50 text-blue-600 rounded-full hover:bg-blue-100 transition-colors"
            >
              <Sparkles size={12} />
              AI 推荐标签
            </button>
          </div>
        )}

        <div
          ref={contentRef}
          className="prose-custom mb-6"
        >
          <HighlightedMarkdown content={highlight.text} annotations={annotations} />

          <div className="mt-4 pt-4 border-t border-dashed border-gray-200 text-center text-xs text-gray-400">
            选中文字可添加高亮或笔记
          </div>
        </div>

        {/* Tags display */}
        {tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-4 border-t border-gray-100">
            {tags.map((tag) => (
              <span key={tag} className="tag tag-gray">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {suggestedTags.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-100">
            {suggestedTags.map((tag) => (
              <button
                key={tag}
                onClick={e => handleAddTag(tag, e)}
                className="tag tag-blue hover:bg-blue-100 transition-colors cursor-pointer"
              >
                + {tag}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="card p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">笔记与高亮</h3>

        <div className="mb-6">
          <textarea
            id="note-input"
            value={newNote}
            onChange={e => setNewNote(e.target.value)}
            placeholder="添加笔记...（选中文字后会在下方显示）"
            className="textarea"
            rows={3}
          />
          {selectedText && (
            <div className="mt-3 p-3 bg-yellow-50 text-sm text-gray-600 rounded-lg border border-yellow-100">
              <span className="font-medium">选中内容: </span>{selectedText}
            </div>
          )}
          <button
            onClick={handleAddNote}
            disabled={!newNote.trim() && !selectedText}
            className="mt-3 btn btn-primary"
          >
            <Plus size={16} className="inline mr-1" />
            添加笔记
          </button>
        </div>

        {annotations.length === 0 ? (
          <p className="text-center py-6 text-gray-400">暂无笔记，选中文字后可添加高亮或笔记</p>
        ) : (
          <div className="space-y-4">
            {annotations.map((annotation, index) => (
              <div
                key={annotation.id}
                ref={el => annotationRefs.current[index] = el}
                className={`annotation cursor-pointer ${selectedAnnotationIndex === index ? 'ring-2 ring-blue-400 rounded-lg' : ''}`}
                onClick={() => setSelectedAnnotationIndex(index)}
              >
                {annotation.selected_text && (
                  <div className="annotation-quote bg-yellow-50 border-l-4 border-yellow-400">
                    "{annotation.selected_text}"
                  </div>
                )}
                {editingAnnotationId === annotation.id ? (
                  <div className="mt-2" onClick={e => e.stopPropagation()}>
                    <textarea
                      className="textarea w-full"
                      rows={3}
                      value={editingNote}
                      onChange={e => setEditingNote(e.target.value)}
                      autoFocus
                    />
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={e => handleSaveAnnotationNote(annotation.id, e)}
                        className="btn btn-primary text-sm py-1"
                      >
                        保存
                      </button>
                      <button
                        onClick={e => { e.stopPropagation(); setEditingAnnotationId(null); }}
                        className="btn btn-secondary text-sm py-1"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    {annotation.note ? (
                      <div className="annotation-note">{annotation.note}</div>
                    ) : (
                      <div className="text-gray-400 text-sm italic mt-1">（无评价文本）</div>
                    )}
                  </>
                )}
                <div className="annotation-meta flex items-center justify-between mt-2">
                  <span>{new Date(annotation.created_at).toLocaleString()}</span>
                  <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={e => handleEditAnnotation(annotation, e)}
                      className="text-gray-400 hover:text-blue-500 transition-colors text-xs"
                    >
                      {annotation.note ? '编辑评价' : '添加评价'}
                    </button>
                    <button
                      onClick={e => handleDeleteAnnotation(annotation.id, e)}
                      className="text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {menuPos && (
        <div
          ref={menuRef}
          className="fixed z-50 flex items-center bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden"
          style={{ left: menuPos.x, top: menuPos.y }}
        >
          <button
            onMouseDown={e => {
              e.preventDefault();
              const copyText = selectedText;
              if (navigator.clipboard) {
                navigator.clipboard.writeText(copyText).catch(() => {
                  const ta = document.createElement('textarea');
                  ta.value = copyText;
                  ta.style.cssText = 'position:fixed;opacity:0';
                  document.body.appendChild(ta);
                  ta.select();
                  document.execCommand('copy');
                  document.body.removeChild(ta);
                });
              } else {
                const ta = document.createElement('textarea');
                ta.value = copyText;
                ta.style.cssText = 'position:fixed;opacity:0';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
              }
              window.getSelection()?.removeAllRanges();
              setMenuPos(null);
              setSelectedText('');
            }}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 whitespace-nowrap transition-colors"
          >
            <Copy size={14} className="text-gray-500" />
            复制
          </button>
          <div className="w-px h-5 bg-gray-200 flex-shrink-0" />
          <button
            onMouseDown={e => {
              e.preventDefault();
              handleAddHighlightOnly(e);
            }}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-yellow-600 hover:bg-yellow-50 whitespace-nowrap transition-colors"
          >
            <Highlighter size={14} />
            高亮
          </button>
          <div className="w-px h-5 bg-gray-200 flex-shrink-0" />
          <button
            onMouseDown={e => {
              e.preventDefault();
              setMenuPos(null);
              setTimeout(() => {
                const input = document.getElementById('note-input');
                if (input) {
                  input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  input.focus();
                }
              }, 50);
            }}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-blue-600 hover:bg-blue-50 whitespace-nowrap transition-colors"
          >
            <Plus size={14} />
            笔记
          </button>
        </div>
      )}
    </div>
  );
}
