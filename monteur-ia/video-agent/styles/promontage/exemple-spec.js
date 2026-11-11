// Short: "Génération sacrifiée", style ProMontage. All times are SOURCE seconds.
//  0-2     accroche sur fond sombre : "Génération" + "sacrifiée ?" doré
//  3-9.6   caméra floutée : "Depuis le Covid : on a tout subi." + compteur 2019 -> 2026
//  12.5    tampon "TRÈS GRAVE" sur la caméra
//  17-23   caméra floutée : "Nos relations deviennent étranges." + carte de points
//  39-54   fond sombre : la liste de l'école
//  54.4    tampon "DOMMAGE." sur la caméra
const IMG = n => `assets/images/${n}.png`;
const W = '#F3EEE4';
const BG = { k: 'glass', dark: true, x: 0, y: 0, w: 1080, h: 1920, r: 0, tint: .5, blur: 26, cut: true };
const T1 = (text, at) => ({ k: 'text', text, size: 64, weight: 800, color: W, align: 'left', x: 72, y: 300, at });
const T2 = (text, at) => ({ k: 'text', text, size: 120, color: '#D8B46A', align: 'left', x: 72, y: 410, at });
const row = (y, icon, text, at) => [
  { k: 'img', img: IMG(icon), s: 76, x: 130, y, at, pop: .6 },
  { k: 'text', text, size: 58, weight: 600, color: W, align: 'left', x: 200, y, at },
];
window.SPEC = {
  title: 'Génération sacrifiée',
  media: {},
  cam: { crop: [0, 0, 1080, 1920], eyes: [529, 1165] },
  cut: [[55.25, 55.81]],
  layout: { keys: [[0, 1920], [2.05, 0], [38.9, 1920], [54.1, 0]] },
  zoom: { keys: [[0, 1]] },
  actors: [],
  scenes: [
    { type: 'board', from: 0, to: 2.0, pre: .5, items: [
      { k: 'text', text: 'Génération', size: 96, weight: 800, color: W, align: 'left', x: 72, y: 820, at: 0, shown: true },
      { k: 'text', text: 'sacrifiée ?', size: 150, color: '#D8B46A', align: 'left', x: 72, y: 960, at: 0, shown: true },
    ] },
    { type: 'board', layer: 'over', from: 3.1, to: 9.6, items: [
      { ...BG, at: 3.1 },
      T1('Depuis le Covid :', 3.15),
      T2('on a tout subi.', 6.43),
      { k: 'img', img: IMG('face-with-medical-mask'), s: 110, x: 540, y: 690, at: 4.12 },
      { k: 'counter', value: 2026, fromValue: 2019, sep: '', size: 160, x: 540, y: 860, at: 4.12, countFrom: 4.4, countTo: 7.0 },
      { k: 'stamp', text: 'ÉNORMÉMENT.', size: 80, x: 540, y: 1100, at: 9.21 },
    ] },
    { type: 'board', layer: 'over', from: 12.4, to: 13.4, items: [
      { k: 'stamp', text: 'TRÈS GRAVE', size: 100, x: 540, y: 1560, at: 12.53 },
    ] },
    { type: 'board', layer: 'over', from: 17.2, to: 23.2, items: [
      { ...BG, at: 17.2 },
      T1('Nos relations', 17.63),
      T2('deviennent étranges.', 21.35),
      { k: 'dots', cols: 7, rows: 4, gap: 96, r: 22, x: 540, y: 800, at: 17.8, groups: [{ i0: 0, n: 28, at: 18.25, color: 'blue' }, { i0: 0, n: 28, at: 21.35, color: 'ink3' }] },
    ] },
    { type: 'board', from: 38.9, to: 54.1, items: [
      { k: 'text', text: "À l'école", size: 64, weight: 800, color: W, align: 'left', x: 72, y: 720, at: 39.26 },
      { k: 'text', text: 'rien ne va.', size: 120, color: '#D8B46A', align: 'left', x: 72, y: 830, at: 40.5 },
      ...row(1010, 'snowflake', 'Pas de chauffage', 42.46),
      ...row(1110, 'hourglass', 'Attente pour manger', 44.35),
      ...row(1210, 'hourglass', 'Journées trop longues', 49.34),
      ...row(1310, 'sleeping-face', 'Élèves fatigués', 51.27),
      ...row(1410, 'chart-decreasing', 'Aucune progression', 52.49),
    ] },
    { type: 'board', layer: 'over', from: 54.3, items: [
      { k: 'stamp', text: 'DOMMAGE.', size: 120, x: 540, y: 1560, at: 54.45 },
    ] },
  ],
  music: { bed: 'enquete', offset: 0 },
  sfx: { swish: 0, accents: 0, extra: [[9.21, 'thud', -6], [12.53, 'thud', -6], [54.45, 'thud', -4]] },
  captions: {
    replace: [['fondis.', 'fondées.'], ['Sous-titrage', ''], ['Société', ''], ['Radio-Canada', '']],
    emph: ['Covid', 'grave.', 'étrange.', 'sociabiliser.', 'd\'efforts.', 'manifestations.', 'fondées.', 'écoles,', 'dommage.'],
    hide: [[0, 2.0], [39.2, 54.1]],
    yKeys: [[0, 330], [3.1, 1480], [9.7, 330], [17.2, 1480], [23.3, 330]],
  },
};
