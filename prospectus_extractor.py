from abc import abstractmethod, ABC

class ProspectusExtractor(ABC):
    @abstractmethod
    def extract_document(self, doc):
        pass

