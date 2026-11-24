const test=require('node:test'),assert=require('node:assert/strict'),katex=require('../frontend/vendor/katex/katex.min.js');
test('bundled math renderer handles limits fractions and scripts',()=>{
 const html=katex.renderToString(String.raw`\lim_{x\to0}\frac{1-\cos x}{x^2}=\frac12`,{throwOnError:true,trust:false});
 assert.ok(html.includes('katex'));assert.ok(html.includes('mfrac'));
});
