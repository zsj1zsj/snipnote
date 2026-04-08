/**
 * Generate and download a Markdown file for a highlight.
 * @param {object} highlight - highlight object
 * @param {Array}  annotations - optional array of annotation objects
 */
export function exportHighlightAsMarkdown(highlight, annotations = []) {
  const lines = [];

  // Title
  const title = highlight.source || `摘录 #${highlight.id}`;
  lines.push(`# ${title}`);
  lines.push('');

  // Meta
  if (highlight.author) lines.push(`**作者：** ${highlight.author}`);
  if (highlight.tags) lines.push(`**标签：** ${highlight.tags.split(',').map(t => `#${t.trim()}`).join(' ')}`);
  if (highlight.created_at) lines.push(`**创建时间：** ${highlight.created_at}`);
  if (highlight.location) lines.push(`**来源：** ${highlight.location}`);
  lines.push('');
  lines.push('---');
  lines.push('');

  // Body
  lines.push(highlight.text || '');
  lines.push('');

  // Summary
  if (highlight.summary) {
    lines.push('---');
    lines.push('');
    lines.push('## 摘要');
    lines.push('');
    lines.push(highlight.summary);
    lines.push('');
  }

  // Annotations
  if (annotations.length > 0) {
    lines.push('---');
    lines.push('');
    lines.push('## 批注');
    lines.push('');
    annotations.forEach((ann, i) => {
      lines.push(`### 批注 ${i + 1}`);
      if (ann.created_at) lines.push(`*${ann.created_at}*`);
      lines.push('');
      if (ann.selected_text) {
        lines.push(`> "${ann.selected_text}"`);
        lines.push('');
      }
      if (ann.note) {
        lines.push(ann.note);
        lines.push('');
      }
    });
  }

  const content = lines.join('\n');
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title.replace(/[/\\:*?"<>|]/g, '_')}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
