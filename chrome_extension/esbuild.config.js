const esbuild = require('esbuild');

const options = {
  entryPoints: {
    background: 'src/background.ts',
    chatgpt: 'src/content/chatgpt.ts',
    claude: 'src/content/claude.ts',
    clipper: 'src/content/clipper.ts',
    instagram: 'src/content/instagram.ts',
    twitter: 'src/content/twitter.ts',
    twitter_main: 'src/content/twitter_main.ts',
    popup: 'src/popup/popup.ts',
  },
  bundle: true,
  outdir: 'dist',
  format: 'iife',
  target: 'chrome120',
};

if (process.argv.includes('--watch')) {
  esbuild.context(options).then((ctx) => ctx.watch());
} else {
  esbuild.build(options).catch(() => process.exit(1));
}
