import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, Star, Check, Trash2, Plus, Lightbulb, ExternalLink, Sparkles, Highlighter } from 'lucide-react';
import api from '../api';

// Custom components to Render highlights in markdown
function HighlightedMarkdown({ content, annotations }) {
  const annotationsWithText = annotations?.filter(a => a.selected_text && a.selected_text.trim()) || [];

  if (annotationsWithText.length === 0) {
    return <ReactMarkdown>{content}</ReactMarkdown>;
  }

  const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = annotationsWithText
    .map(a => a.selected_text.trim())
    .sort((a, b) => b.length - a.length);

  if (patterns.length === 0) {
    return <ReactMarkdown>{content}</ReactMarkdown>;
  }

  const pattern = new RegExp(`(${patterns.map(escapeRegex).join('|')})`, 'gi');

  const parts = content.split(pattern);

  if (parts.length === 1) {
    return <ReactMarkdown>{content}</ReactMarkdown>;
  }

  return (
    <ReactMarkdown
      components={{
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
}

function extractText(children) {
  if (!children) return '';
  if (typeof children === 'string') return children;
  if (Array.isArray(children)) return children.map(extractText).join('');
  if (children.props?.children) return extractText(children.props.children);
  return '';
}

export default function HighlightDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
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
  const scrollPositionRef = useRef(0);

  const loadHighlight = useCallback(async (saveScroll = false) => {
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
  }, [id]);

  useEffect(() => {
    loadHighlight();
  }, [id]);

  const handleToggleFavorite = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.toggleFavorite(id).then(updated => {
      setData(prev => ({ ...prev, highlight: updated }));
    });
  }, [id]);

  const handleToggleRead = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.toggleRead(id).then(updated => {
      setData(prev => ({ ...prev, highlight: updated }));
    });
  }, [id]);

  const handleDelete = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!confirm('确定要删除这条摘录吗？')) return;
    api.deleteHighlight(id).then(() => {
      navigate('/highlights');
    });
  }, [id, navigate]);

  const handleAddHighlightOnly = useCallback((e) => {
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
  }, [id, selectedText]);

  const handleAddNote = useCallback((e) => {
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
  }, [id, selectedText, newNote]);

  const handleDeleteAnnotation = useCallback((annotationId, e) => {
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
  }, [id]);

  const handleSuggestTags = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    api.suggestTags(data.highlight.text, data.highlight.tags || '').then(result => {
      setSuggestedTags(result.tags);
    }).catch(console.error);
  }, [data]);

  const handleSummarize = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const currentScroll = window.scrollY;
    api.summarize(data.highlight.text).then(result => {
      setSummary(result.summary);
      return api.updateHighlight(id, { summary: result.summary });
    }).then(() => {
      return api.highlight(id);
    }).then(result => {
      setData(prev => ({ ...prev, highlight: { ...prev.highlight, summary: result.highlight.summary } }));
      setTimeout(() => window.scrollTo(0, currentScroll), 0);
    }).catch(console.error);
  }, [data, id]);

  const handleAddTag = useCallback((tagName, e) => {
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
  }, [data, id]);

  const handleContextMenu = useCallback((e) => {
    const selection = window.getSelection();
    const text = selection ? selection.toString().trim() : '';

    if (text && text.length > 0) {
      e.preventDefault();
      e.stopPropagation();
      setSelectedText(text);

      const menuWidth = 200;
      const menuHeight = 120;
      let x = e.clientX;
      let y = e.clientY;

      if (x + menuWidth > window.innerWidth) {
        x = window.innerWidth - menuWidth - 10;
      }
      if (y + menuHeight > window.innerHeight) {
        y = window.innerHeight - menuHeight - 10;
      }

      setMenuPos({ x, y });
    } else {
      setMenuPos(null);
      setSelectedText('');
    }
  }, []);

  useEffect(() => {
    const handleClick = () => setMenuPos(null);
    document.addEventListener('click', handleClick);

    const handleDocumentContextMenu = (e) => {
      const selection = window.getSelection();
      const text = selection ? selection.toString().trim() : '';
      if (text && text.length > 0) {
        e.preventDefault();
      }
    };
    document.addEventListener('contextmenu', handleDocumentContextMenu);

    return () => {
      document.removeEventListener('click', handleClick);
      document.removeEventListener('contextmenu', handleDocumentContextMenu);
    };
  }, []);

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
          navigate('/highlights');
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

        <div
          ref={contentRef}
          className="prose-custom mb-6"
          onContextMenu={handleContextMenu}
        >
          <HighlightedMarkdown content={highlight.text} annotations={annotations} />

          <div className="mt-4 pt-4 border-t border-dashed border-gray-200 text-center text-xs text-gray-400">
            选中文字后右键可添加高亮或笔记
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-5 border-t border-gray-100">
          {tags.map((tag) => (
            <span key={tag} className="tag tag-gray">
              #{tag}
            </span>
          ))}
          <button
            onClick={handleSuggestTags}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            <Sparkles size={12} />
            AI 推荐标签
          </button>
        </div>

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

        {summary && (
          <div className="mt-5 p-4 bg-gradient-to-r from-amber-50 to-yellow-50 rounded-lg border border-amber-100">
            <div className="flex items-center gap-2 text-sm font-medium text-amber-700 mb-2">
              <Lightbulb size={16} />
              摘要
            </div>
            <p className="text-gray-700">{summary}</p>
          </div>
        )}

        {!summary && (
          <button
            onClick={handleSummarize}
            className="mt-5 flex items-center gap-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            <Sparkles size={14} />
            使用 AI 生成摘要
          </button>
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
          <p className="text-center py-6 text-gray-400">暂无笔记，选中文字后右键添加高亮或笔记</p>
        ) : (
          <div className="space-y-4">
            {annotations.map((annotation) => (
              <div key={annotation.id} className="annotation">
                {annotation.selected_text && (
                  <div className="annotation-quote bg-yellow-50 border-l-4 border-yellow-400">
                    "{annotation.selected_text}"
                  </div>
                )}
                {annotation.note && (
                  <div className="annotation-note">
                    {annotation.note}
                  </div>
                )}
                <div className="annotation-meta flex items-center justify-between">
                  <span>{new Date(annotation.created_at).toLocaleString()}</span>
                  <button
                    onClick={e => handleDeleteAnnotation(annotation.id, e)}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {menuPos && (
        <div
          className="fixed bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 min-w-[180px]"
          style={{ left: menuPos.x, top: menuPos.y }}
          onClick={e => e.stopPropagation()}
        >
          <button
            onClick={handleAddHighlightOnly}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-yellow-50 text-gray-700 flex items-center gap-2 transition-colors"
          >
            <Highlighter size={14} className="text-yellow-500" />
            添加高亮
          </button>
          <button
            onClick={e => {
              e.preventDefault();
              e.stopPropagation();
              setMenuPos(null);
              // Scroll to note input and focus
              setTimeout(() => {
                const input = document.getElementById('note-input');
                if (input) {
                  input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  input.focus();
                }
              }, 50);
            }}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-blue-50 text-gray-700 flex items-center gap-2 transition-colors"
          >
            <Plus size={14} className="text-blue-500" />
            添加笔记
          </button>
        </div>
      )}
    </div>
  );
}
