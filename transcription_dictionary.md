# Transcription Post-Processing Dictionary

## Format
Each entry: `raw_term | correct_term | context_hint | model`
- `raw_term` — what the model outputs (case-insensitive matching)
- `correct_term` — what it should be
- `context_hint` — when to apply (empty = always, otherwise check surrounding words)
- `model` — which model produces this error (parakeet_mlx, canary, both, any)

## Direct Substitutions
<!-- Same every time, no context needed -->
```
яйка | AI | | both
яйку | AI | | both
яйці | AI | | both
яйком | AI | | both
Бімат | BMAD | | both
обімат | BMAD | | both
Бейсу | base | | both
безсу | base | | canary
кодегенератор | code generator | | parakeet_mlx
кодегенератора | code generator | | both
деплой | deploy | | both
стейджінг | staging | | both
продакшн | production | | both
рефакторінг | refactoring | | both
ендпоінт | endpoint | | both
бекенд | backend | | both
фронтенд | frontend | | both
кульпреп | call prep | | both
кульпрепи | call preps | | both
кульпрепі | call prep | | both
пайн-поінт | pain point | | both
пайн-пойнт | pain point | | both
пейн-пойнт | pain point | | both
пайн-поінти | pain points | | both
фалбек | fallback | | both
фалбеків | fallbacks | | both
скіл | skill | agent context | both
скріпт | script | | both
```

## Company & Product Names
```
Софтджорн | Softjourn | | both
Сіневе | Cinewave | | both
Сіневеїв | Cinewave | | both
Сіновеєва | Cinewave | | both
Навейво | Cinewave | | parakeet_mlx
Паксом | PAX | | both
Пакс | PAX | | both
припайт | Paypod | | both
припайд | Paypod | | both
```

## People Names
```
Гробенко | Горбенко | Діма context | canary
Тріщуком | Тріщуком | | ok
Тричука | Тріщука | | parakeet_mlx
Тричук | Тріщук | | parakeet_mlx
Любчик | Любчик | | ok
Романів | Романів | | ok
Марені | Марині | | both
Маріяна | Мар'яна | | both
```

## Context-Dependent
<!-- Same word maps to different corrections depending on context -->
```
Ренді | R&D | meeting/work context | both
РНД | R&D | | both
скрайпінг | scraping | web/data context | both
скрепет | scrape | web context | both
бойлерплей | boilerplate | code/template context | both
```

## Tech Terms (Code-Switching uk+en)
```
Google С | Google SX | | parakeet_mlx
селес-асістанта | Sales Assistant | | both
селес-асістент | Sales Assistant | | both
хаб-спот | HubSpot | | parakeet_mlx
Хобспот | HubSpot | | parakeet_mlx
```
