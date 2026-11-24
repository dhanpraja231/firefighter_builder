# Vendored MMD loader

`MMDLoader`, `MMDAnimationHelper`, `MMDToonShader` and `mmdparser.module.js` are copied unchanged
from `three@0.171.0/examples/jsm` (MIT, three.js authors), because three removed them in r172 and
this app uses three 0.180. The only edits are import paths, dropping the deprecation warning, and
stubbing out `MMDPhysics` (physics isn't used).

They load `public/pmx/Firefighter.pmx`, the model every firefighter robot role uses.
