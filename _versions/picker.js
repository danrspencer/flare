/**
 * The docs' version picker, loaded by every page of every version from
 * the site root (scripts/docs_site.py adds it), so one copy serves them
 * all. Reads versions.json beside it, puts a picker in the header, and
 * says so on a page that isn't the latest release.
 */
(() => {
  // Where a page sits: the latest release at the root, a release under
  // v/<version>/, the beta under beta/. `rest` is the page within it.
  function locate(path, base, versions) {
    const inside = path.startsWith(base) ? path.slice(base.length) : '';
    const release = inside.match(/^v\/([^/]+)\/(.*)$/);
    if (release) return { kind: 'release', version: release[1], rest: release[2] };
    const beta = inside.match(/^beta\/(.*)$/);
    if (beta) return { kind: 'beta', version: versions.beta, rest: beta[1] };
    return { kind: 'latest', version: versions.latest, rest: inside };
  }

  // Every version offered, newest release first, the beta last.
  function options(base, versions, rest) {
    const latestRelease = versions.releases[0];
    const list = versions.releases.map((version) => ({
      version,
      label: version === latestRelease ? `${version} (latest)` : version,
      url: version === latestRelease ? base + rest : `${base}v/${version}/${rest}`,
    }));
    if (versions.beta) {
      // With no release yet, the beta is what the root serves.
      const url = latestRelease ? `${base}beta/${rest}` : base + rest;
      list.push({ version: versions.beta, label: `${versions.beta} (beta)`, url });
    }
    return list;
  }

  // Says which docs these are, unless they're the latest release's.
  function notice(here, versions) {
    const latestRelease = versions.releases[0];
    if (here.kind === 'beta' && latestRelease) {
      return { text: `These are the docs for the beta, ${here.version}.`, link: 'the latest release' };
    }
    if (here.kind === 'release' && here.version !== latestRelease) {
      return { text: `These are the docs for FLARE ${here.version}.`, link: 'the latest release' };
    }
    if (here.kind === 'latest' && !latestRelease && versions.beta) {
      return { text: `There's no release yet: these are the docs for the beta, ${versions.beta}.` };
    }
    return null;
  }

  globalThis.FlareVersions = { locate, options, notice };
  if (typeof document === 'undefined') return;

  const script = document.currentScript;
  const versionsDir = new URL('.', script.src);
  const base = new URL('..', versionsDir).pathname;

  async function go(url, fallback) {
    try {
      const res = await fetch(url, { method: 'HEAD' });
      window.location.href = res.ok ? url : fallback;
    } catch {
      window.location.href = fallback;
    }
  }

  function render(versions) {
    const here = locate(window.location.pathname, base, versions);
    const choices = options(base, versions, here.rest);
    if (!choices.length) return;

    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Docs version');
    select.style.cssText = 'font: inherit; padding: 2px 4px; margin: 0 8px; border-radius: 4px;';
    for (const choice of choices) {
      const option = document.createElement('option');
      option.value = choice.url;
      option.textContent = choice.label;
      option.selected = choice.version === here.version;
      select.appendChild(option);
    }
    select.addEventListener('change', () => {
      const choice = choices[select.selectedIndex];
      go(choice.url, choice.url.slice(0, choice.url.length - here.rest.length));
    });

    const aux = document.querySelector('.aux-nav-list');
    if (aux) {
      const item = document.createElement('li');
      item.className = 'aux-nav-list-item';
      item.style.cssText = 'display: flex; align-items: center;';
      item.appendChild(select);
      aux.prepend(item);
    } else {
      select.style.cssText += 'position: fixed; top: 8px; right: 8px; z-index: 100;';
      document.body.appendChild(select);
    }

    const said = notice(here, versions);
    const main = document.querySelector('#main-content') || document.querySelector('main');
    if (said && main) {
      const box = document.createElement('p');
      box.className = 'note';
      box.textContent = `${said.text} `;
      if (said.link) {
        const a = document.createElement('a');
        a.href = base + here.rest;
        a.textContent = `See ${said.link}.`;
        box.appendChild(a);
      }
      main.prepend(box);
    }
  }

  fetch(new URL('versions.json', versionsDir))
    .then((res) => (res.ok ? res.json() : null))
    .then((versions) => versions && render(versions))
    .catch(() => {});
})();
