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
геймеритом | гаймеритом | | both
геймерит | гаймерит | | both
гейморетивно | гайморетивно | | both
ГМР | гайморитом | | both
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
нежи | нежить | | both
улиця | вулиця | | both
ренхен | рентген | | both
Сурі | Сорі | | both
молода | молодець | | both
Сіди | Сяді | | both
реалізами | релізами | | both
файлів | фейлів | sales/fail context | both
Рінкедин | Лінкедин | | both
LOR | ЛОР | | both
КПС | капець | | both
скрипав | скрейпав | web context | both
скриптипт | скрипт | | both
ап-ключ | апі-ключ | | both
фалбеків | фолбеків | | both
клот | Claude | | both
ассенд | ассесменту | architecture context | both
інфумента | імпрувменту | | both
сфестифікована | софістикейтед | | both
стрітфор | стрейтфор | | both
скаювати | скейлити | | both
сотлери | thought leaders | | both
Фрам | промпт | | both
хабає | хапає | | both
```

## Company & Product Names
```
Софтджорн | Softjourn | | both
Spectric | Spectrix | | both
Статрікс | Спектрікс | | both
спектрів | спектрікс | | both
Сіневе | Cinewave | | both
Сіневеїв | Cinewave | | both
Сіновеєва | Cinewave | | both
Навейво | Cinewave | | parakeet_mlx
Паксом | PAX | | both
Пакс | PAX | | both
припайт | Prepaid | | both
припайд | Prepaid | | both
припайдіть | Prepaid | | both
припайдами | Prepaid | | both
пакст | PEX | | both
PAX | PEX | | both
Texails | Tech Sales | | both
Upsideal | Upsale | | both
sluishens | solutions | | both
Івен Брайт | Event Brite | | both
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
Луара | Лора | ЛОР context | both
Хазер | Хезер | | both
Сезар | Хезер | | both
Ліані | Мар'яні | | both
```

## Context-Dependent
<!-- Same word maps to different corrections depending on context -->
```
Ренді | R&D | meeting/work context | both
РНД | R&D | | both
скрайпінг | scraping | web/data context | both
скрепет | scrape | web context | both
колкрапи | call preps | | both
колпрепи | call preps | | both
пров'ю | персонал рев'ю | | both
СВП | CV | | both
експлуатажне | експектейшни | | both
екстанс | експенс | | both
аудит.диту | аудиту | | both
ткенгу | тікетингу | | both
обтіки | в тікетингу | | both
докофісу | бекофісу | | both
атукух | аплікух | | both
бойлерплей | boilerplate | code/template context | both
```

## Tech Terms (Code-Switching uk+en)
```
Google С | Google SX | | parakeet_mlx
селес-асістанта | Sales Assistant | | both
селес-асістент | Sales Assistant | | both
хаб-спот | HubSpot | | parakeet_mlx
Хобспот | HubSpot | | parakeet_mlx
standing | expense | employee context | both
Ding Dissycle | Ticketing Recycle | | both
```
