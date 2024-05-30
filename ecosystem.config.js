module.exports = {
  apps: [
    {
      name: 'moxa-api',
      script: 'app.py',
      interpreter: '~/miniconda3/envs/moxa-api/bin/python',  // Update this path
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
