import asyncio
import os
import json

import httpx
import aiofiles.tempfile
import aiofiles

organization = "AmanoTeam"

ignore_mirroring = set()

class Repository:
	
	def __init__(self, id, name, description):
		self.id = id
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
			"namespace_id": 2981821,
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
	
	status = response.status_code in (200, 400)
	
	response = await client.post(
		url = "https://gitlab.com/api/v4/projects/AmanoTeam%%2f%s/repository/branches" % (name),
		json = {
			"branch": "master",
			"ref": "main"
		},
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	response = await client.put(
		url = "https://gitlab.com/api/v4/projects/AmanoTeam%%2F%s" % (name),
		json = {
			"default_branch": "master"
		},
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	return status

async def forgejo_create_repository(
	client,
	instance,
	name,
	description = None
):
	
	(user, password) = (
		instance["user"],
		instance["password"]
	)
	
	response = await client.post(
		url = "https://%s/api/v1/user/repos" % (user),
		data = {
			"name": name,
			"description": "" if description is None else description,
			"has_actions": "false"
		},
		headers = {
			"Authorization": "token %s" % password
		}
	)
	data = response.json()
	
	status = response.status_code in (200, 201, 409, 500)
	
	if not status:
		print("error: %s" % str(data))
	
	return status

async def forgejo_purge_orphaned(
	client,
	instance,
	repositories
):
	
	(user, password) = (
		instance["user"],
		instance["password"]
	)
	
	response = await client.get(
		url = "https://%s/api/v1/user/repos" % (user),
		headers = {
			"Authorization": "token %s" % password
		},
		params = {
			"limit": 100
		}
	)
	data = response.json()
	print(data, user)
	github_repositories = set(repository.name for repository in repositories)
	forgejo_repositories = set(item["name"] for item in data)
	
	for repository in forgejo_repositories:
		if repository in github_repositories:
			continue
		
		print("- Deleting orphaned '%s' from %s" % (repository, user))
		
		response = await client.delete(
			url = "https://%s/api/v1/repos/AmanoTeam/%s" % (user, repository),
			headers = {
				"Authorization": "token %s" % password
			}
		)

async def gitlab_unprotect_branches(client, repository):
	
	gitlab_token = os.getenv(key = "GL_TOKEN")
	
	response = await client.get(
		url = "https://gitlab.com/api/v4/projects/%i/protected_branches" % (repository),
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	for branch in data:
		name = branch["name"]
		
		print("- Deleting branch protections for branch '%s'" % (name))
		
		response = await client.delete(
			url = "https://gitlab.com/api/v4/projects/%i/protected_branches/%s" % (repository, name),
			headers = {
				"Authorization": "Bearer %s" % gitlab_token
			}
		)
	
	return response.status_code == 200

async def mirror(client):
	
	github_token = os.getenv(key = "GH_TOKEN")
	gitlab_token = os.getenv(key = "GL_TOKEN")
	
	github_repositories = []
	gitlab_repositories = []
	forgejo_instances = None
	
	text = None
	
	async with aiofiles.open(file = "./forgejo.json") as file:
		text = await file.read()
	
	forgejo_instances = json.loads(s = text)
	
	data = []
	
	for page_number in range(1, 16):
		response = await client.get(
			url = "https://api.github.com/users/%s/repos" % (organization),
			params = {
				"per_page": 100,
				"page": page_number
			},
			headers = {
				"Authorization": "Bearer %s" % github_token
			}
		)
		items = response.json()
		
		if not items:
			break
		
		data += items
	
	async with aiofiles.open(file = "mirroring-third-party.txt") as file:
		text = await file.read()
	
	for line in text.splitlines():
		name = line.split()[2]
		ignore_mirroring.add(name)
	
	for repository in data:
		(full_name, private, description) = (
			repository["full_name"],
			repository["private"],
			repository["description"],
		)
		
		if private:
			continue
		
		if full_name in ignore_mirroring:
			continue
		
		name = (
			full_name
				.split(sep = "/", maxsplit = 1)
				.pop(-1)
		)
		
		repo = Repository(
			id = None,
			name = name,
			description = description
		)
		
		github_repositories.append(repo)
	
	for instance in forgejo_instances:
		status = await forgejo_purge_orphaned(
			client = client,
			instance = instance,
			repositories = github_repositories
		)
	
	response = await client.get(
		url = "https://gitlab.com/api/v4/groups/AmanoTeam/projects",
		params = {
			"per_page": 100
		},
		headers = {
			"Authorization": "Bearer %s" % gitlab_token
		}
	)
	data = response.json()
	
	for repository in data:
		(id, name) = (
			repository["id"],
			repository["name"]
		)
		
		repo = Repository(
			id = id,
			name = name,
			description = None
		)
		
		await gitlab_unprotect_branches(
			client = client,
			repository = repo.id
		)
		
		gitlab_repositories.append(repo)
	
	for repository in github_repositories:
		status = True
		
		status = await gitlab_create_repository(
			client = client,
			name = repository.name,
			description = repository.description
		)
		
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
			
			print("- Deleting unnecessary refs")
			
			process = await asyncio.create_subprocess_shell(
				cmd = "git -C '%s' for-each-ref --format='delete %%(refname)' refs/pull | git -C '%s' update-ref --stdin" % (
					directory,
					directory
				)
			)
			await process.communicate()
			
			process = await asyncio.create_subprocess_exec(
				*(
					"git",
					"-C",
					directory,
					"symbolic-ref",
					"--short",
					"HEAD"
				),
				stdout = asyncio.subprocess.PIPE,
				stderr = asyncio.subprocess.PIPE
			)
			(stdout, stderr) = await process.communicate()
			
			default_branch = stdout.decode().strip()
			
			if default_branch != "master":
				print("- Renaming default branch from %s to %s" % (default_branch, "master"))
				
				process = await asyncio.create_subprocess_exec(*("git", "-C", directory, "branch", "-m", default_branch, "master"))
				await process.communicate()
				
				default_branch = "master"
				
				process = await asyncio.create_subprocess_exec(*("git", "-C", directory, "symbolic-ref", "HEAD", "refs/heads/" + default_branch))
				await process.communicate()
			
			url = "https://glab:%s@gitlab.com/%s/%s.git" % (
				gitlab_token,
				organization,
				repository.name
			)
			
			print("- Mirroring GitHub repository from '%s' to '%s'" % (directory, url))
			
			process = await asyncio.create_subprocess_exec(*("git", "-C", directory, "push", "--force", "--quiet", "--mirror", url))
			await process.communicate()
			
			for instance in forgejo_instances:
				status = await forgejo_create_repository(
					client = client,
					instance = instance,
					name = repository.name,
					description = repository.description
				)
				
				if not status:
					continue
				
				(user, password) = (
					instance["user"],
					instance["password"]
				)
				
				url = "https://user:%s@%s/%s/%s.git" % (
					password,
					user,
					organization,
					repository.name
				)
				
				print("- Mirroring GitHub repository from '%s' to '%s'" % (directory, url))
				
				retries = 0
				
				while True:
					retries += 1
					
					if retries > 3:
						break
					
					process = await asyncio.create_subprocess_exec(
						*("git", "-C", directory, "push", "--force", "--quiet", "--mirror", url),
						stdout = asyncio.subprocess.PIPE,
						stderr = asyncio.subprocess.PIPE
					)
					(stdout, stderr) = await process.communicate()
					
					if "HTTP 413" in stderr.decode():
						break
					
					if process.returncode != 0:
						continue
					
					break
				

async def main():
	
	async with httpx.AsyncClient(http2 = True, timeout = None) as client:
		await mirror(client = client)

asyncio.run(main())
