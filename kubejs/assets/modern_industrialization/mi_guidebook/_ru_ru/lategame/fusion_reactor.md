---
navigation:
  title: "Термоядерный синтез"
  icon: "modern_industrialization:fusion_reactor"
  position: 302
  parent: modern_industrialization:endgame.md
item_ids:
  - modern_industrialization:fusion_reactor
  - modern_industrialization:plasma_turbine
---

# Термоядерный синтез

## Термоядерный реактор

<GameScene zoom="1" interactive={true} fullWidth={true}>
    <MultiblockShape controller="fusion_reactor" />
</GameScene>

Термоядерный реактор — самый мощный источник энергии. Он превращает дейтерий, тритий и гелий-3 в разных сочетаниях в гелиевую плазму, самое мощное топливо в игре. Для запуска реакции понадобится много энергии.

<Recipe id="modern_industrialization:electric_age/machine/fusion_reactor_asbl" />

## Плазменная турбина

<GameScene zoom="2" interactive={true} fullWidth={true}>
    <MultiblockShape controller="plasma_turbine" />
</GameScene>

Плазменная турбина даёт 100 кEU с каждого милливедра гелиевой плазмы. Максимальная мощность — примерно 1 МEU/такт.

<Recipe id="modern_industrialization:electric_age/machine/plasma_turbine_asbl" />
