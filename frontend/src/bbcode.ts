export const parseBBCode = (text: string | null | undefined): string => {
  if (!text) return 'No description provided by author.';

  let html = text
    // Escape HTML to prevent injection
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

    // Bold, Italic, Underline, Strikethrough
    .replace(/\[b\]/gi, '<strong>').replace(/\[\/b\]/gi, '</strong>')
    .replace(/\[i\]/gi, '<em>').replace(/\[\/i\]/gi, '</em>')
    .replace(/\[u\]/gi, '<u>').replace(/\[\/u\]/gi, '</u>')
    .replace(/\[s\]/gi, '<del>').replace(/\[\/s\]/gi, '</del>')

    // Headers / Size
    .replace(/\[size=(["']?)([0-9]+)\1\]/gi, (_match, _quote, size) => {
      const num = parseInt(size, 10);
      // Rough mapping from BBCode size to rem
      let rem = 1;
      if (num === 1) rem = 0.75;
      else if (num === 2) rem = 0.875;
      else if (num === 3) rem = 1;
      else if (num === 4) rem = 1.125;
      else if (num === 5) rem = 1.5;
      else if (num === 6) rem = 2.0;
      else if (num >= 7) rem = 2.5;
      return `<strong style="font-size: ${rem}rem; display: block; margin: 1rem 0 0.5rem 0; line-height: 1.2;">`;
    })
    .replace(/\[\/size\]/gi, '</strong>')

    // Color & Font
    .replace(/\[color=(["']?)([^"'\]]+)\1\]/gi, (_match, _quote, color) => {
      let c = color;
      if (/^[0-9a-fA-F]{3,8}$/.test(c)) c = '#' + c;
      return `<span style="color: ${c}">`;
    })
    .replace(/\[\/color\]/gi, '</span>')
    .replace(/\[font=(["']?)([^"'\]]+)\1\]/gi, '<span style="font-family: $2">')
    .replace(/\[\/font\]/gi, '</span>')

    // Links
    .replace(/\[url=(["']?)(https?:\/\/[^"'\]]+)\1\](.*?)\[\/url\]/gi, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--accent-hover); text-decoration: underline;">$3</a>')
    .replace(/\[url=(["']?)([^"'\]]+)\1\](.*?)\[\/url\]/gi, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--accent-hover); text-decoration: underline;">$3</a>') // fallback for non-http links
    .replace(/\[url\]([^\[]+)\[\/url\]/gi, '<a href="$1" target="_blank" rel="noopener noreferrer" style="color: var(--accent-hover); text-decoration: underline;">$1</a>')

    // Images
    .replace(/\[img\](.*?)\[\/img\]/gi, '<img src="$1" alt="Image" style="max-width: 100%; border-radius: 8px; margin: 1rem 0; box-shadow: 0 4px 12px rgba(0,0,0,0.3);" />')

    // Alignment
    .replace(/\[center\]/gi, '<div style="text-align: center;">').replace(/\[\/center\]/gi, '</div>')
    .replace(/\[left\]/gi, '<div style="text-align: left;">').replace(/\[\/left\]/gi, '</div>')
    .replace(/\[right\]/gi, '<div style="text-align: right;">').replace(/\[\/right\]/gi, '</div>')

    // Layout
    .replace(/\[indent\]/gi, '<div style="margin-left: 2rem; border-left: 2px solid var(--glass-border); padding-left: 1rem;">').replace(/\[\/indent\]/gi, '</div>')

    // Lists
    .replace(/\[list\](.*?)\[\/list\]/gis, '<ul style="margin-left: 2rem; margin-bottom: 1rem;">$1</ul>')
    .replace(/\[list=1\](.*?)\[\/list\]/gis, '<ol style="margin-left: 2rem; margin-bottom: 1rem;">$1</ol>')
    .replace(/\[\*\]/gi, '<li style="margin-bottom: 0.25rem;">')

    // Code
    .replace(/\[code\](.*?)\[\/code\]/gis, '<pre style="background: rgba(0,0,0,0.5); padding: 1rem; border-radius: 6px; overflow-x: auto; margin: 1rem 0; font-family: monospace;"><code>$1</code></pre>')

    // YouTube
    .replace(/\[youtube\](.*?)\[\/youtube\]/gi, '<a href="https://www.youtube.com/watch?v=$1" target="_blank" style="display: inline-flex; align-items: center; gap: 0.5rem; color: #ef4444; font-weight: 500; background: rgba(239, 68, 68, 0.1); padding: 0.5rem 1rem; border-radius: 6px; text-decoration: none;">▶ Watch on YouTube</a>')

    // Convert newlines to breaks (after everything else so we don't break block tags too badly)
    .replace(/\n/g, '<br/>');

  return html;
};

export const stripBBCode = (text: string | null | undefined): string => {
  if (!text) return 'No description provided by author.';

  // Remove entire image/youtube tags and their contents
  let stripped = text.replace(/\[img\].*?\[\/img\]/gi, ' ');
  stripped = stripped.replace(/\[youtube\].*?\[\/youtube\]/gi, ' ');

  // Extract link text
  stripped = stripped.replace(/\[url=(["']?)([^"'\]]+)\1\](.*?)\[\/url\]/gi, '$3');
  stripped = stripped.replace(/\[url\](.*?)\[\/url\]/gi, '$1');
  
  // General BBCode tag stripper (safely matches known tags)
  stripped = stripped.replace(/\[\/?(b|i|u|s|size|color|font|url|img|center|left|right|justify|indent|list|code|youtube|\*)(=[^\]]*)?\]/gi, ' ');
  
  // Convert newlines to spaces for card view
  stripped = stripped.replace(/\n/g, ' ').replace(/\s{2,}/g, ' ');

  // Strip residual HTML just in case
  const tmp = document.createElement('DIV');
  tmp.innerHTML = stripped;
  const rawText = tmp.textContent || tmp.innerText || '';
  
  return rawText.length > 150 ? rawText.substring(0, 150) + '...' : rawText;
};
