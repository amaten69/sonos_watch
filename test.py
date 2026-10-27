mys = "<DidlMusicTrack 'b'Over the Rainbow'' at 0x1675c2ffc40>"
start = mys.find("'x'")
end = mys.find("''")

print(f"{start} - {end}")
print(mys[start+3:end])
