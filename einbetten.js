/*
 * Marktübersicht auf einer fremden Website einbinden.
 *
 *   <div data-marktuebersicht data-seite="aktien" data-abschnitte="weltmarkt,bewertung"></div>
 *   <script src="https://<adresse-der-marktuebersicht>/einbetten.js" async></script>
 *
 * data-seite        Seite wie in der Adresse nach #/, z. B. aktien, aktien/usa, immobilien, rohstoffe (leer = Startseite)
 * data-abschnitte   Kennungen der Sektionen, kommagetrennt (leer = alle Sektionen der Seite)
 * data-hintergrund  "transparent" übernimmt den Hintergrund der einbettenden Seite
 * data-titel        Titel des Rahmens für Screenreader
 * Die Höhe passt sich automatisch dem Inhalt an.
 */
(function () {
  var skript = document.currentScript;
  var basis = skript ? skript.src.replace(/einbetten\.js(\?.*)?$/, '') : '';
  var zaehler = 0;

  function einbauen(el) {
    if (el.getAttribute('data-mu-fertig')) return;
    el.setAttribute('data-mu-fertig', '1');
    var id = 'mu' + (++zaehler) + '-' + Math.random().toString(36).slice(2, 7);
    var seite = el.getAttribute('data-seite') || '';
    var abschnitte = el.getAttribute('data-abschnitte') || '';
    var adresse = basis + '?einbetten=1&id=' + encodeURIComponent(id) +
      (abschnitte ? '&abschnitte=' + encodeURIComponent(abschnitte) : '') +
      (el.getAttribute('data-hintergrund') === 'transparent' ? '&hintergrund=transparent' : '') +
      (seite ? '#/' + seite.replace(/^#?\/?/, '') : '');
    var rahmen = document.createElement('iframe');
    rahmen.src = adresse;
    rahmen.title = el.getAttribute('data-titel') || 'Marktübersicht';
    rahmen.loading = 'lazy';
    rahmen.setAttribute('data-mu-id', id);
    rahmen.style.cssText = 'display:block;width:100%;border:0;min-height:240px;';
    el.appendChild(rahmen);
  }

  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d || d.typ !== 'marktuebersicht-hoehe' || !d.id) return;
    var rahmen = document.querySelector('iframe[data-mu-id="' + d.id + '"]');
    if (rahmen && ev.source === rahmen.contentWindow) rahmen.style.height = Math.ceil(d.hoehe) + 'px';
  });

  function alle() {
    var liste = document.querySelectorAll('[data-marktuebersicht]');
    for (var i = 0; i < liste.length; i++) einbauen(liste[i]);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', alle); else alle();
})();
