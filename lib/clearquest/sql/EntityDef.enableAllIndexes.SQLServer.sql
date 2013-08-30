#for index in this.listIndexes()
ALTER INDEX ${index} ON ${this.GetDbName()} REBUILD
#end