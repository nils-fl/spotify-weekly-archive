// pm2 one-shot job.
//
// autorestart:false + cron_restart means pm2 runs the script at each cron hit
// and lets it exit, rather than respawning it as a daemon.
//
// The cron expression is evaluated in the server's local timezone. 09:00 Monday
// is chosen to fall after Discover Weekly's overnight refresh.
//
// All paths are derived from this file's location, so the project works from
// wherever it is checked out.
const path = require('path');

const root = __dirname;

module.exports = {
  apps: [
    {
      name: 'spotify-weekly-archive',
      script: 'src/sync.py',
      cwd: root,
      interpreter: path.join(root, '.venv', 'bin', 'python'),
      env: { PYTHONPATH: path.join(root, 'src') },
      cron_restart: '0 9 * * 1',
      autorestart: false,
      time: true,
      out_file: path.join(root, 'logs', 'pm2-out.log'),
      error_file: path.join(root, 'logs', 'pm2-err.log'),
    },
  ],
};
