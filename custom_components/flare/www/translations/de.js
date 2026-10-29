// The dashboard's German text, based on the translation stefanr09
// contributed in danrspencer/flare#301.
export default {
  'phase.morning': 'Morgen',
  'phase.day': 'Tag',
  'phase.evening': 'Abend',
  'phase.night': 'Nacht',

  'schedule.badge_phase': 'Phase',
  'schedule.badge_brightness': 'Helligkeit',
  'schedule.badge_colour': 'Farbe',
  'schedule.badge_override': 'Überschreiben',
  'schedule.override': 'Überschreiben',
  'schedule.override_phase': 'Phase',
  'schedule.override_sticky': 'Dauerhaft',
  'schedule.times': 'Zeitplan',
  'schedule.evening_earliest': 'Abend (frühestens)',
  'schedule.evening_latest': 'Abend (spätestens)',
  'schedule.curve': 'Kurve',
  'schedule.curve_kelvin': '{phase}-Farbtemperatur',
  'schedule.curve_brightness': '{phase}-Helligkeit',
  'schedule.transitions': 'Übergänge',
  'schedule.transitions_note':
    'Wie lange vor dem Ende jeder Phase mit dem Übergang zur nächsten begonnen wird, in Minuten. ' +
    '0 ist ein harter Schnitt. Werte werden auf die Phase begrenzt; alles, was länger als die Phase selbst ist, ' +
    'bedeutet „Übergang über die ganze Phase“.',
  'schedule.transition_kelvin': '{phase}-Farbe',
  'schedule.transition_brightness': '{phase}-Helligkeit',
  'schedule.transfer': 'Kopieren oder Einfügen',

  'curve.missing_entity': 'Entität fehlt: {entity}',
  'curve.evening_starts': 'Abend beginnt um {time}.',
  'curve.evening_starts_because': 'Abend beginnt um {time}, {reason}.',
  'curve.capped_latest': 'begrenzt auf die späteste Grenze ({bound}) — der heutige Sonnenuntergang ist später, um {sunset}',
  'curve.capped_earliest': 'begrenzt auf die früheste Grenze ({bound}) — der heutige Sonnenuntergang ist früher, um {sunset}',
  'curve.following_sunset': 'folgt dem heutigen Sonnenuntergang',
  'curve.populating': '(Kurve wird noch gefüllt — sie aktualisiert sich jede Minute)',
  'curve.sunrise': 'Sonnenaufgang {time}',
  'curve.sunset': 'Sonnenuntergang {time}',
  'curve.now': 'Jetzt {time}',
  'curve.brightness': '{value} Helligkeit',
  'curve.sun_up': 'Sonne auf',
  'curve.sun_down': 'Sonne unter',

  'transfer.prompt': 'Diesen Zeitplan zum Sichern oder Teilen kopieren – oder einen einfügen.',
  'transfer.copy': 'Kopieren',
  'transfer.paste': 'Einfügen',
  'transfer.placeholder': 'Zeitplan hier einfügen',
  'transfer.cancel': 'Abbrechen',
  'transfer.apply': 'Übernehmen',
  'transfer.no_schedule': 'Kein FLARE-Zeitplan-Sensor {sensor}.',
  'transfer.copied': 'Kopiert.',
  'transfer.copy_by_hand': 'Kopiere den Zeitplan aus dem Feld oben.',
  'transfer.imported': 'Zeitplan importiert.',

  'view.lighting': 'Beleuchtung',
  'view.no_schedules':
    'Noch keine FLARE-Zeitpläne gefunden.\n\nFüge einen unter **Einstellungen → Geräte & Dienste → FLARE → ' +
    'Zeitplan hinzufügen** hinzu, dann erscheint er hier automatisch.',
  'view.unknown_schedule': 'Kein FLARE-Zeitplan namens `{name}`.\n\nVorhandene Zeitpläne:\n\n{available}',
  'view.no_settings':
    'Der **Einstellungen**-Eintrag von FLARE ist nicht eingerichtet, also verfolgt nichts, welche Lampen FLARE ' +
    'steuert. Füge FLARE unter **Einstellungen → Geräte & Dienste** hinzu.',
  'view.overrides': 'Überschreibungen',
  'view.activity': 'Aktivität',
  'view.no_lights':
    'Noch keine Lampen. Eine Lampe erscheint hier, sobald die Automation ihres Raums sie gesetzt hat, ' +
    'nach Bereich gruppiert.',

  'overrides.all_lights': 'Alle Lampen',
  'overrides.controlled': 'Gesteuert',
  'overrides.overridden': 'Überschrieben',
  'overrides.clear_all': 'Alle zurücksetzen',
  'overrides.areas': 'Bereiche',
  'overrides.other_areas': 'Weitere Bereiche',
  'overrides.count_controlled': '{count} gesteuert',
  'overrides.count_overridden': '{count} überschrieben',
  'overrides.clear_light': '{name} zurücksetzen',
  'overrides.asked_showing': 'Angefordert {asked}, zeigt {showing}',
  'overrides.asked': 'Angefordert {asked}',
  'overrides.showing': 'Zeigt {showing}',
  'overrides.off': 'aus',
  'overrides.on': 'an',
  'overrides.unavailable': 'nicht verfügbar',

  'status.controlled': 'Gesteuert',
  'status.overridden': 'Überschrieben',
  'status.mismatched': 'Abweichend',
  'status.untracked': 'Nicht verfolgt',
  'status.unavailable': 'Nicht verfügbar',

  'activity.all': 'Alle',
  'activity.controlled': 'Gesteuert',
  'activity.overridden': 'Überschrieben',
  'activity.cleared': 'Zurückgesetzt',

  'clear.name': 'Zurücksetzen',
};
