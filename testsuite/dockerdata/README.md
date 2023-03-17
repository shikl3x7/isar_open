# Creating image

```
export version="3.2.2"
cd <isar_dir>/testsuite/dockerdata
sed "s/:latest/:${version}/" Dockerfile | docker build -t ghcr.io/ilbers/docker-isar:${version} -
```

# Pushing the image to docker hub

- Configure github token (classic) with `write:packages` permissions.

- Use it for uploading docker image:

```
export version="3.2.2"
docker push ghcr.io/ilbers/docker-isar:${version}
```

- Make the uploaded package public 
