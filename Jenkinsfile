pipeline {
    agent {
        docker {
            image 'ghcr.io/siemens/kas/kas-isar:3.2.1'
            args '-u 0 -e USER_ID="$(id -u)" -e GROUP_ID="$(id -g)"'
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
        stage('Build and run') {
            steps {
                sh "./scripts/ci_build.sh -T ${params.TAGS}"
            }
        }
    }
}
