/* SIGNAL 看板交互：分类 / 重要度 / 搜索 / 视图切换 */
(function () {
  'use strict';

  var DATA = window.NEWS_DATA || null;
  var state = { category: 'all', importance: 'all', query: '', view: 'cards' };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtWindow(s) {
    if (!s) return '—';
    return String(s).replace('T', ' ').slice(0, 16);
  }

  function showNotice(text) {
    var n = document.getElementById('notice');
    if (text) document.getElementById('noticeText').textContent = text;
    n.hidden = false;
    ['metrics', 'briefGrid', 'controls', 'leads'].forEach(function (id) {
      document.getElementById(id).hidden = true;
    });
  }

  function init() {
    if (!DATA || !DATA.leads || !DATA.leads.length) {
      showNotice();
      return;
    }

    document.getElementById('metaWindow').textContent =
      fmtWindow(DATA.window.start) + ' → ' + fmtWindow(DATA.window.end);
    document.getElementById('metaGenerated').textContent = fmtWindow(DATA.generatedAt);
    var seal = document.getElementById('metaStatus');
    seal.textContent = '数据已载入';
    seal.className = 'issue-seal ready';

    var s = DATA.stats || {};
    document.getElementById('mFetched').textContent = s.fetched || 0;
    document.getElementById('mValid').textContent = s.valid || 0;
    document.getElementById('mLeads').textContent = s.leads || (DATA.leads || []).length;
    document.getElementById('mSources').textContent = s.sources || 0;

    document.getElementById('briefText').textContent = DATA.brief || '暂无研判内容。';

    var cross = document.getElementById('crossList');
    if (DATA.crossDomain && DATA.crossDomain.length) {
      DATA.crossDomain.forEach(function (x) {
        var li = document.createElement('li');
        li.textContent = x;
        cross.appendChild(li);
      });
    } else {
      cross.innerHTML = '<li>暂无跨领域关联观察</li>';
    }

    buildChips();
    bindControls();
    render();
  }

  function buildChips() {
    var box = document.getElementById('categoryChips');
    var cats = DATA.categories || {};
    var all = document.createElement('button');
    all.type = 'button';
    all.className = 'chip active';
    all.textContent = '全部 ' + (DATA.leads || []).length;
    all.setAttribute('data-category', 'all');
    box.appendChild(all);

    Object.keys(cats).forEach(function (key) {
      var count = (DATA.leads || []).filter(function (l) { return l.category === key; }).length;
      if (!count) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip';
      btn.setAttribute('data-category', key);
      var dot = document.createElement('span');
      dot.className = 'chip-dot';
      dot.style.color = cats[key].color || '#e8a33d';
      btn.appendChild(dot);
      btn.appendChild(document.createTextNode(cats[key].label + ' ' + count));
      box.appendChild(btn);
    });
  }

  function bindControls() {
    document.getElementById('categoryChips').addEventListener('click', function (e) {
      var btn = e.target.closest('.chip');
      if (!btn) return;
      state.category = btn.getAttribute('data-category');
      Array.prototype.forEach.call(this.querySelectorAll('.chip'), function (b) {
        b.classList.toggle('active', b === btn);
      });
      render();
    });

    document.getElementById('importanceFilter').addEventListener('click', function (e) {
      var btn = e.target.closest('.seg');
      if (!btn) return;
      state.importance = btn.getAttribute('data-value');
      Array.prototype.forEach.call(this.querySelectorAll('.seg'), function (b) {
        b.classList.toggle('active', b === btn);
      });
      render();
    });

    document.getElementById('viewSwitch').addEventListener('click', function (e) {
      var btn = e.target.closest('.view-btn');
      if (!btn) return;
      state.view = btn.getAttribute('data-view');
      Array.prototype.forEach.call(this.querySelectorAll('.view-btn'), function (b) {
        b.classList.toggle('active', b === btn);
      });
      render();
    });

    document.getElementById('searchInput').addEventListener('input', function (e) {
      state.query = e.target.value.trim().toLowerCase();
      render();
    });

    document.getElementById('resetBtn').addEventListener('click', function () {
      state = { category: 'all', importance: 'all', query: '', view: state.view };
      document.getElementById('searchInput').value = '';
      Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (b, i) {
        b.classList.toggle('active', i === 0);
      });
      Array.prototype.forEach.call(document.querySelectorAll('.seg'), function (b) {
        b.classList.toggle('active', b.getAttribute('data-value') === 'all');
      });
      render();
    });
  }

  function filtered() {
    return (DATA.leads || []).filter(function (l) {
      if (state.category !== 'all' && l.category !== state.category) return false;
      if (state.importance !== 'all' && l.importance !== state.importance) return false;
      if (state.query) {
        var hay = [l.title, l.summary, l.impact, (l.key_facts || []).join(' '),
          (l.entities || []).join(' '), (l.sources || []).map(function (s) { return s.publisher; }).join(' ')]
          .join(' ').toLowerCase();
        if (hay.indexOf(state.query) === -1) return false;
      }
      return true;
    });
  }

  function catColor(key) {
    return ((DATA.categories || {})[key] || {}).color || '#e8a33d';
  }

  function catLabel(key) {
    return ((DATA.categories || {})[key] || {}).label || key;
  }

  function leadHTML(lead, index) {
    var color = catColor(lead.category);
    var parts = [];
    parts.push('<article class="lead" style="--cat-color:' + esc(color) + '">');
    parts.push('<div class="lead-rail"><span class="lead-no">' + String(index + 1).padStart(2, '0') + '</span><span class="lead-rail-line"></span></div>');
    parts.push('<div class="lead-body">');
    parts.push('<div class="lead-top">');
    parts.push('<span class="cat-tag">' + esc(catLabel(lead.category)) + '</span>');
    parts.push('<span class="importance-tag ' + esc(lead.importance) + '">' + esc(importanceText(lead.importance)) + '</span>');
    parts.push('<span class="confidence-tag">可信度 · ' + esc(confidenceText(lead.confidence)) + '</span>');
    parts.push('</div>');
    parts.push('<h3 class="lead-title">' + esc(lead.title) + '</h3>');
    parts.push('<p class="lead-summary">' + esc(lead.summary) + '</p>');

    if (lead.entities && lead.entities.length) {
      parts.push('<div class="entity-row">');
      lead.entities.forEach(function (e) { parts.push('<span class="entity">' + esc(e) + '</span>'); });
      parts.push('</div>');
    }

    parts.push('<div class="lead-details">');
    if (lead.key_facts && lead.key_facts.length) {
      parts.push('<div class="detail-block"><span class="detail-label">关键事实</span><ul>');
      lead.key_facts.forEach(function (f) { parts.push('<li>' + esc(f) + '</li>'); });
      parts.push('</ul></div>');
    }
    if (lead.impact) {
      parts.push('<div class="detail-block"><span class="detail-label">影响研判</span><p class="impact-text">' + esc(lead.impact) + '</p></div>');
    }
    if (lead.followups && lead.followups.length) {
      parts.push('<div class="detail-block"><span class="detail-label">待跟踪</span><ul>');
      lead.followups.forEach(function (f) { parts.push('<li>' + esc(f) + '</li>'); });
      parts.push('</ul></div>');
    }
    if (lead.sources && lead.sources.length) {
      parts.push('<div class="detail-block"><span class="detail-label">信源 · ' + lead.sources.length + '</span><ul class="source-list">');
      lead.sources.forEach(function (src) {
        parts.push('<li><span class="source-pub">' + esc(src.publisher) + '</span>' +
          '<a href="' + esc(src.url) + '" target="_blank" rel="noopener noreferrer">' + esc(src.title) + '</a></li>');
      });
      parts.push('</ul></div>');
    }
    parts.push('</div></div></article>');
    return parts.join('');
  }

  function timelineHTML(lead) {
    var color = catColor(lead.category);
    var time = (lead.sources && lead.sources[0] && lead.sources[0].published_at) || '时间未标注';
    return '<div class="timeline-item" style="--cat-color:' + esc(color) + '">' +
      '<div class="timeline-time">' + esc(fmtWindow(time)) + ' · ' + esc(catLabel(lead.category)) + '</div>' +
      leadHTML(lead, 0) + '</div>';
  }

  function importanceText(v) {
    return { high: '高重要度', medium: '中重要度', low: '低重要度' }[v] || v;
  }

  function confidenceText(v) {
    return { high: '高', medium: '中', low: '低' }[v] || v;
  }

  function render() {
    var items = filtered();
    var box = document.getElementById('leads');
    document.getElementById('resultCount').textContent = '显示 ' + items.length + ' / ' + (DATA.leads || []).length + ' 条';
    document.getElementById('emptyState').hidden = items.length > 0;

    if (!items.length) {
      box.innerHTML = '';
      return;
    }

    if (state.view === 'timeline') {
      box.innerHTML = '<div class="timeline">' + items.map(timelineHTML).join('') + '</div>';
    } else {
      box.innerHTML = items.map(leadHTML).join('');
    }
  }

  init();
})();
