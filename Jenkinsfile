pipeline {
    agent {
      node {
        label "built-in"
        customWorkspace "/build/$JOB_NAME/$BUILD_ID"
      }
    }
    options {
        disableConcurrentBuilds()
        timestamps()
    }
    parameters {
        choice(name: 'TAGS', choices: ['dev', 'fast', 'full'], description: 'TAGS to execute')
    }
    environment {
        DISTRO_APT_PREMIRRORS = 'deb.debian.org ftp.de.debian.org'
    }
    stages {
        stage('Stage') {
            parallel {
                stage('Cleanup') {
                    steps {
                        sh "/home/workspace/bin/clean_task.sh"
                    }
                }
                stage('Build and run') {
                    steps {
                        sh "/home/workspace/bin/build_task.sh '-T ${params.TAGS}'"
                    }
                }
            }
        }
    }
}
