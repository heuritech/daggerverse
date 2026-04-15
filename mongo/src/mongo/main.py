import dagger
from dagger import dag, function, object_type, Doc, field

import dataclasses
from typing import Annotated, Self


@object_type
class Mongo:
    image: Annotated[str, Doc("The image to use")] = "mongo"
    version: Annotated[str, Doc("The version of mongodb to use")] = "7.0.16"
    user: Annotated[dagger.Secret | None, Doc("The mongodb user")] = field()
    password: Annotated[dagger.Secret | None, Doc("The password of the mongodb user")] = field()
    hostname: Annotated[str, Doc("The mongo hostname to use (only used for mongo uri helper")] = field(default="mongodb.service")
    __ctr: dagger.Container = dataclasses.field(init=False)

    def __post_init__(self):
        if self.user is None:
            self.user = dag.set_secret("MONGO_INITDB_ROOT_USERNAME", "mongo")

        if self.password is None:
            self.password = dag.set_secret("MONGO_INITDB_ROOT_PASSWORD", "mongo")

        self.__ctr = (
                dag.
                container().
                from_(f"{self.image}:{self.version}").
                with_secret_variable("MONGO_INITDB_ROOT_USERNAME", self.user).
                with_secret_variable("MONGO_INITDB_ROOT_PASSWORD", self.password).
                with_exposed_port(27017)
        )

    @function
    async def with_init_data(self, data: dagger.Directory) -> Self:
        """Allow to add json data to mongo"""
        self.__ctr = (
            self.
            __ctr.
            with_mounted_directory("/tmp/data", data)
        )
        return self

    @function
    async def with_init_scripts(self, scripts: dagger.Directory) -> Self:
        """Allow to add bash oa js script for the mongo setup"""
        self.__ctr = (
            self.
            __ctr.
            with_mounted_directory("/docker-entrypoint-initdb.d/", scripts)
        )
        return self

    @function
    async def with_data(self, data: dagger.Directory) -> Self:
        """Allow to mount a snapshot/backup data folder"""
        self.__ctr = (
            self.
            __ctr.
            with_mounted_directory("/data/db", data)
        )
        return self

    @function
    async def uri(self) -> dagger.Secret:
       return dag.set_secret(
           "MONGODB_URI",
           f"mongodb://{await self.user.plaintext()}:{await self.password.plaintext()}@{self.hostname}:27017/",
       )

    @function
    async def with_hostname(self, hostname: str) -> Self:
        """Allow to add json data to mongo"""
        self.hostname = hostname

        return Self

    @function
    async def service(self) -> dagger.Service:
        """Expose a mongo container as a service"""

        return (
            self.
            __ctr.
            as_service(
                use_entrypoint=True,
                args=["mongod", "--quiet"],
            )
            .with_hostname(self.hostname)
        )

    @function
    async def ctr(self) -> dagger.Container:
        """Get the mongodb container"""
        return self.__ctr

    @function
    async def ci_test(self) -> str:
        """Only for poc / troubleshot / ci"""
        svc = await self.service()
        uri = await self.uri()
        return await (
            self.
            __ctr.
            with_service_binding(
                await svc.hostname(),
                svc,
            ).
            with_exec([
                "mongosh",
                await uri.plaintext(),
                "--eval",
                "\"db.runCommand({ ping: 1 })\"",
            ]).
            stdout()
        )
