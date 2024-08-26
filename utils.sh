function mirror() {
	
	local directory="$(mktemp --directory)"
	local source="${1}"
	local destination="${2}"
	
	local secret="${3}"
	
	local url="https://github:${secret}@github.com/${destination}"
	
	echo "- Mirroring third-party repository from '${source}' to '${destination}'"
	
	git clone --quiet --mirror "${source}" "${directory}"
	
	git -C "${directory}" push --force --quiet --branches "${url}"
	git -C "${directory}" push --force --quiet --tags "${url}"
	
}
