module.exports = {
  apps : [{
    name: 'clueless',
    cmd: 'src/main.py',
    autorestart: true,
    watch: true,
    ignore_watch: ["src/utils/database.db","src/utils/database.db-journal"],
    interpreter: 'python3'
  }],

  deploy : {
    production : {
      key  : 'SSH_KEY_PATH',
      user : 'SSH_USERNAME',
      host : 'SSH_HOSTMACHINE',
      ref  : 'origin/main',
      repo : 'GIT_REPOSITORY',
      path : 'DESTINATION_PATH',
    }
  }
};
