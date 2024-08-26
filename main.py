import asyncio
import os

import httpx
import aiofiles.tempfile

organization = "AmanoTeam"

class Repository:
	
	def __init__(self, name, description):
		self.name = name
		self.description = description
	
	def __eq__(self, other):
		return self.name == other.name

async def gitlab_create_repository(client, name, description = None):
	
	gitlab_token = os.getenv(key = "GL_TOKEN")
	
	response = await client.post(
		url = "https://gitlab.com/api/v4/projects",
		json = {
			"default_branch": "master",
			"description": "" if description is None else description,
			"initialize_with_readme": "false",
			"name": name,
			"path": name,
			"visibility": "public",
			"tag_list": []
		},
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	return response.status_code == 200

async def mirror(client):
	
	github_token = os.getenv(key = "GH_TOKEN")
	gitlab_token = os.getenv(key = "GL_TOKEN")
	
	github_repositories = []
	gitlab_repositories = []
	
	response = await client.get(
		url = "https://api.github.com/users/%s/repos" % (organization),
		params = {
			"per_page": 100
		},
		headers = {
			"Authorization": "Bearer %s" % github_token
		}
	)
	data = response.json()
	
	for repository in data:
		(full_name, private, description) = (
			repository["full_name"],
			repository["private"],
			repository["description"],
		)
		
		if private:
			continue
		
		name = (
			full_name
				.split(sep = "/", maxsplit = 1)
				.pop(-1)
		)
		
		repo = Repository(
			name = name,
			description = description
		)
		
		github_repositories.append(repo)
	
	response = await client.get(
		url = "https://gitlab.com/api/v4/projects",
		params = {
			"owned": "true",
			"per_page": 100
		},
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	for repository in data:
		(name) = (
			repository["name"]
		)
		
		repo = Repository(
			name = name,
			description = None
		)
		
		gitlab_repositories.append(repo)
	
	for repository in github_repositories:
		status = True
		
		if repository not in gitlab_repositories:
			status = await gitlab_create_repository(
				client = client,
				name = repository.name,
				description = repository.description
			)
		
		if not status:
			continue
		
		async with aiofiles.tempfile.TemporaryDirectory() as temporary_directory:
			directory = temporary_directory
			
			url = "https://github.com/%s/%s.git" % (
				organization,
				repository.name
			)
			
			print("- Cloning GitHub repository from '%s' to '%s'" % (url, directory))
			
			process = await asyncio.create_subprocess_exec(
				*(
					"git",
					"clone",
					"--quiet",
					"--mirror",
					url,
					directory
				)
			)
			
			await process.communicate()
			
			url = "https://glab:%s@gitlab.com/%s-mirror/%s.git" % (
				gitlab_token,
				organization,
				repository.name
			)
			
			print("- Mirroring GitHub repository from '%s' to '%s'" % (directory, url))
			
			process = await asyncio.create_subprocess_exec(
				*(
					"git",
					"-C", directory,
					"push",
					"--quiet",
					"--mirror",
					url
				)
			)
			
			await process.communicate()

async def main():
	
	async with httpx.AsyncClient(http2 = True) as client:
		await mirror(client = client)

asyncio.run(main())
